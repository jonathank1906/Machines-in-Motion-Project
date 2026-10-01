import asyncio
import os
import re
import socket
import time
import xml.etree.ElementTree as ET

# Server frames look like this (XML declaration, multi-line header, body ending in "\n\0"):
#   <?xml version="1.0" encoding="UTF-8"?>\n<xmlh>\n  <xml size="740"/>\n</xmlh><lc .../>\n\0
HEADER_RE = re.compile(rb'(?:<\?xml[^>]*\?>\s*)?<xmlh>\s*<xml\b([^>]*?)/?>\s*</xmlh>')
NEXT_FRAME_RE = re.compile(rb'(?:<\?xml[^>]*\?>\s*)?<xmlh>')
SIZE_RE = re.compile(rb'size="(\d+)"')
NAME_RE = re.compile(rb'name="([^"]*)"')
WS = b" \r\n\t\x00"

# Lenient fallback if ElementTree rejects a body
TAG_RE = re.compile(r'<(lc|sw)\s([^>]*?)/?>')
ATTR_RE = re.compile(r'([\w:.-]+)="([^"]*)"')


class RocrailAdapter:
    """
    Design notes (learned from probing Rocrail):
      * Live lc/sw events are broadcast to every connected client, so listening tracks all changes.
      * Rocrail doesn't push state on connect, so we ask for it with <model cmd="lclist"/> (and swlist),
        on connect and periodically. These requests are safe.
      * NEVER request <model cmd="plan"/>: Rocrail flags us as an "alien" client and drops the connection.
      * Until Rocrail answers, state comes from plan.xml (mostly zeros). Each entry has
        "source": "plan" | "live" so you can tell what has been confirmed by Rocrail.
      * Commands go over short-lived separate connections so they can't disturb the listener.
    """

    def __init__(self, host="127.0.0.1", port=8051, log_frames=False,
                 resync_interval=30, sync_switches=True):
        self.host = host
        self.port = port
        self.log_frames = log_frames
        self.resync_interval = resync_interval  # seconds between lclist refreshes (0 = only on connect)
        self.sync_switches = sync_switches      # also request swlist (auto-disabled if it gets us dropped)
        self._connected_at = 0.0
        self._swlist_sent = False

        base = os.path.join(os.path.dirname(__file__), '..')
        self.plan_file = os.path.join(base, 'plan.xml')

        self.reader = None
        self.writer = None
        self.connected = False
        self._stopping = False
        self._task = None
        self.state = {
            "status": "offline",
            "locomotives": {},
            "switches": {},
            "debug": {"bytes_received": 0, "frames": 0, "last_event": None,
                      "disconnects": 0, "last_disconnect": None},
        }
        self.load_plan()

    def _log(self, msg):
        print(f"[rocrail] {msg}", flush=True)

    # ---------- initial state from plan.xml (replaced by live data once Rocrail answers) ----------
    def load_plan(self):
        try:
            root = ET.parse(self.plan_file).getroot()
            for lc in root.iter('lc'):
                self._apply_lc(dict(lc.attrib), "plan")
            for sw in root.iter('sw'):
                self._apply_sw(dict(sw.attrib), "plan")
            self._log(f"loaded {len(self.state['locomotives'])} locomotives and "
                      f"{len(self.state['switches'])} switches from plan.xml")
        except Exception as e:
            self._log(f"could not load plan.xml: {e}")

    # ---------- state updates ----------
    def _apply_lc(self, attrs, source="live"):
        loc_id = attrs.get("id")
        if not loc_id:
            return
        loco = self.state["locomotives"].setdefault(loc_id, {"speed": 0, "direction": "forward"})

        # Command echoes carry a cmd attribute; only trust plain state or "velocity"
        if attrs.get("cmd") in (None, "", "velocity"):
            v = attrs.get("V")
            if v is not None:
                try:
                    loco["speed"] = int(float(v))
                    if source == "live":
                        self.state["debug"]["last_event"] = f"{loc_id} V={loco['speed']}"
                except (ValueError, OverflowError):
                    pass
            d = attrs.get("dir")
            if d is not None:
                loco["direction"] = "forward" if d == "true" else "reverse"
        loco["source"] = source

    def _apply_sw(self, attrs, source="live"):
        sw_id = attrs.get("id")
        if not sw_id:
            return
        sw = self.state["switches"].setdefault(sw_id, {"state": "unknown"})
        if attrs.get("state") is not None:
            sw["state"] = attrs.get("state")
        sw["source"] = source

    # ---------- frame handling ----------
    def _handle_frame(self, name, body):
        body = body.strip(WS)
        self.state["debug"]["frames"] += 1
        if self.log_frames:
            self._log(f"frame ({len(body)} bytes): {body[:160]!r}")
        try:
            root = ET.fromstring(body)
            nodes = [(el.tag, dict(el.attrib)) for el in root.iter() if el.tag in ("lc", "sw")]
        except ET.ParseError:
            text = body.decode("utf-8", errors="replace")
            nodes = [(m.group(1), dict(ATTR_RE.findall(m.group(2)))) for m in TAG_RE.finditer(text)]

        for tag, attrs in nodes:
            if tag == "lc":
                self._apply_lc(attrs)
            else:
                self._apply_sw(attrs)

    def _safe_handle(self, name, body):
        try:
            self._handle_frame(name, body)
        except Exception as e:
            self._log(f"error handling frame: {type(e).__name__}: {e}")

    def _process(self, buf):
        """Consume as many complete frames as possible from buf; return the unconsumed remainder."""
        while buf:
            m = HEADER_RE.search(buf)
            if not m:
                idx = [i for i in (buf.find(b"<?xml"), buf.find(b"<xmlh")) if i != -1]
                if idx:
                    return buf[min(idx):]          # header split across reads, wait for more
                self._safe_handle("raw", buf)       # no framing at all: parse leniently
                return b""

            attrs = m.group(1)
            sm, nm = SIZE_RE.search(attrs), NAME_RE.search(attrs)
            size = int(sm.group(1)) if sm else None
            name = nm.group(1).decode(errors="ignore") if nm else "-"
            start = m.end()

            # 1) trust the declared size if what follows is nothing or the next frame
            if size is not None and len(buf) >= start + size:
                rest = buf[start + size:]
                if not rest.strip(WS) or NEXT_FRAME_RE.match(rest.lstrip(WS)):
                    self._safe_handle(name, buf[start:start + size])
                    buf = rest.lstrip(WS)
                    continue

            # 2) declared size is wrong: cut at the next frame header instead
            nxt = NEXT_FRAME_RE.search(buf, start)
            if nxt:
                self._safe_handle(name, buf[start:nxt.start()])
                buf = buf[nxt.start():]
                continue

            # 3) incomplete frame, wait for more data
            return buf[m.start():]
        return b""

    # ---------- listener connection (never sends) ----------
    async def connect(self):
        """Starts the background listener; reconnects automatically."""
        self._stopping = False
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while not self._stopping:
            reason = "unknown"
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                sock = self.writer.get_extra_info("socket")
                if sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.connected = True
                self.state["status"] = "online"
                self._log("connected, requesting current state")
                self._connected_at = time.monotonic()
                self._swlist_sent = False
                await self._request_state()
                reason = await self._listen()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
            finally:
                self.connected = False
                self.state["status"] = "offline"
                if self.writer:
                    self.writer.close()
                    self.writer = None
            if self._swlist_sent and time.monotonic() - self._connected_at < 10:
                self.sync_switches = False
                self._log("dropped right after the swlist request; switch sync disabled")
            self._swlist_sent = False
            self.state["debug"]["disconnects"] += 1
            self.state["debug"]["last_disconnect"] = reason
            self._log(f"disconnected: {reason}")
            if not self._stopping:
                await asyncio.sleep(2)

    async def _request_state(self):
        """Ask Rocrail for the current loco (and switch) state. Never request the full plan."""
        await self._send_on_listener('<model cmd="lclist"/>')
        if self.sync_switches:
            await self._send_on_listener('<model cmd="swlist"/>')
            self._swlist_sent = True

    async def _send_on_listener(self, body):
        payload = body.encode("utf-8")
        header = f'<xmlh><xml size="{len(payload)}" name="model"/></xmlh>'.encode("utf-8")
        self.writer.write(header + payload)  # no bytes after the payload, not even a NUL
        await self.writer.drain()

    async def _listen(self):
        buf = b""
        timeout = self.resync_interval or None
        while True:
            try:
                data = await asyncio.wait_for(self.reader.read(65536), timeout)
            except asyncio.TimeoutError:
                await self._request_state()  # periodic resync
                continue
            if not data:
                return "Rocrail closed the connection (EOF)"
            self.state["debug"]["bytes_received"] += len(data)
            buf = self._process(buf + data)
            if len(buf) > 5_000_000:
                buf = b""

    # ---------- commands: short-lived separate connection ----------
    async def send_command(self, body, name):
        payload = body.encode("utf-8")
        header = f'<xmlh><xml size="{len(payload)}" name="{name}"/></xmlh>'.encode("utf-8")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=3)
        writer.write(header + payload)
        await writer.drain()
        # Keep the socket open briefly (and drain replies) so Rocrail can process it, without blocking the API
        asyncio.create_task(self._linger_and_close(reader, writer))

    @staticmethod
    async def _linger_and_close(reader, writer, seconds=1.5):
        try:
            end = time.monotonic() + seconds
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    data = await asyncio.wait_for(reader.read(65536), remaining)
                except asyncio.TimeoutError:
                    break
                if not data:
                    break
        finally:
            writer.close()

    def disconnect(self):
        self._stopping = True
        self.connected = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self.writer:
            self.writer.close()

    def get_state(self):
        return self.state