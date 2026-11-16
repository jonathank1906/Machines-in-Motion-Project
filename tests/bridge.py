import asyncio
import csv
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import paho.mqtt.client as mqtt
from bleak import BleakClient

BROKER_HOST = "localhost"
BROKER_PORT = 1883
COMMAND_TOPIC = "rocrail/service/command"

# Map Rocrail's Decoder Address (addr) OR Locomotive ID (id) to each physical LEGO Hub
# You can match by addr ("1", "2", "3") or by Rocrail ID ("60337", "snow", "cargo")
TRAIN_CONFIGS = [
    {
        "name": "60337",
        "keys": {"1", "60337"},
        "mac": "9C:9A:C0:4A:8B:B9",
        "has_light": True,
        "direction_sign": 1,
    },
    {
        "name": "60470",
        "keys": {"2", "60470"},
        "mac": "9C:9A:C0:4B:FD:20",
        "has_light": False,
        "direction_sign": 1,
    },
    {
        "name": "60508",
        "keys": {"3", "60508"},
        "mac": "9C:9A:C0:33:9F:EB",
        "has_light": False,
        "direction_sign": 1,
    },
]

MOTOR_PORT = 0x00
LIGHT_PORT = 0x01

MIN_POWER = 22
TOP_POWER = 40
LIGHT_POWER = 40
REVERSE_PAUSE = 0.6
STOP_ON_POWER_OFF = False
LOG_FILE = "latency_log.csv"

HUB_CHAR_UUID = "00001624-1212-efde-1623-785feabcd123"


def report_status(loco_id: str, status: str):
    try:
        url = f"http://localhost:8000/api/bridge/status/{loco_id}/{status}"
        request = urllib.request.Request(url, method="POST")
        urllib.request.urlopen(request, timeout=2)
    except Exception:
        pass


def speed_to_power(v: float, v_max: float) -> int:
    if v <= 0 or v_max <= 0:
        return 0
    fraction = min(v / v_max, 1.0)
    return round(MIN_POWER + fraction * (TOP_POWER - MIN_POWER))


def find_train_config(loco_id: str, addr: str):
    for cfg in TRAIN_CONFIGS:
        if loco_id in cfg["keys"] or addr in cfg["keys"]:
            return cfg
    return None


def interpret(payload: str):
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None

    if root.tag == "lc":
        loco_id = root.get("id", "")
        addr = root.get("addr", "")
        cfg = find_train_config(loco_id, addr)
        if cfg is None:
            return None
        try:
            v = float(root.get("V", "0"))
            v_max = float(root.get("V_max", "100"))
        except ValueError:
            return None
        forward = root.get("dir", "true") == "true"
        power = speed_to_power(v, v_max) * (1 if forward else -1) * cfg["direction_sign"]
        light = root.get("f0", root.get("fn", "false")) == "true"
        return {
            "kind": "loco",
            "mac": cfg["mac"],
            "name": cfg["name"],
            "power": power,
            "light": light,
            "v": v,
            "forward": forward,
            "warn": None if root.get("V_mode", "percent") == "percent"
            else f"V_mode is {root.get('V_mode')}, expected percent",
        }

    if root.tag == "sys":
        cmd = root.get("cmd")
        if cmd in ("stop", "ebreak"):
            return {"kind": "stop_all", "why": f"sys cmd={cmd}"}
        return {"kind": "note", "text": f"sys message: {payload[:120]}"}

    if root.tag == "state":
        if root.get("power") == "false" and STOP_ON_POWER_OFF:
            return {"kind": "stop_all", "why": "power off"}
        return {"kind": "note", "text": f"state message: power={root.get('power')}"}

    return None


class Bridge:
    def __init__(self, name: str, write, has_light: bool = True):
        self.name = name
        self._write = write
        self.has_light = has_light
        self.power = 0
        self.light = False

    async def apply_loco(self, power: int, light: bool):
        if power != self.power:
            reversing = self.power != 0 and power != 0 and (power > 0) != (self.power > 0)
            if reversing:
                print(f"   [{self.name}] direction flipped while moving: stopping first")
                await self._write(MOTOR_PORT, 0)
                self.power = 0
                await asyncio.sleep(REVERSE_PAUSE)
            await self._write(MOTOR_PORT, power)
            self.power = power
        if self.has_light and light != self.light:
            await self._write(LIGHT_PORT, LIGHT_POWER if light else 0)
            self.light = light

    async def stop_motor(self):
        await self._write(MOTOR_PORT, 0)
        self.power = 0

    async def shutdown(self):
        await self.stop_motor()
        if self.has_light:
            await self._write(LIGHT_PORT, 0)
            self.light = False


def log_latency(rx_to_write_ms: float, write_to_ack_ms: float, v, power):
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["time", "rocrail_speed", "power", "mqtt_to_ble_write_ms", "write_to_hub_ack_ms"])
        w.writerow([datetime.now().isoformat(timespec="milliseconds"), v, power,
                    f"{rx_to_write_ms:.1f}", f"{write_to_ack_ms:.1f}"])


async def connect_hub(cfg, last_cmds):
    mac = cfg["mac"]
    name = cfg["name"]
    print(f"Scanning/connecting to {name} ({mac})...")

    def on_disconnected(_client):
        report_status(name, "offline")

    client = BleakClient(
        mac,
        timeout=8.0,
        disconnected_callback=on_disconnected,
    )
    try:
        await client.connect()
    except Exception as exc:
        report_status(name, "offline")
        print(f"   [SKIP] {name} ({mac}) not awake or out of range: {exc}")
        return None, None

    def on_notify(_, data: bytearray):
        cmd_info = last_cmds.get(mac)
        if len(data) >= 4 and data[2] == 0x82 and data[3] == MOTOR_PORT and cmd_info:
            ack_ms = (time.perf_counter() - cmd_info["t_done"]) * 1000
            log_latency(cmd_info["rx_to_write_ms"], ack_ms, cmd_info["v"], cmd_info["power"])
            print(f"   [{name}] latency: MQTT->BLE write {cmd_info['rx_to_write_ms']:.0f} ms, "
                  f"write->hub ack {ack_ms:.0f} ms")
            last_cmds.pop(mac, None)

    await client.start_notify(HUB_CHAR_UUID, on_notify)

    async def write(port_id: int, power: int):
        if not client.is_connected:
            return
        p = max(-TOP_POWER, min(TOP_POWER, power)) if port_id == MOTOR_PORT else power
        data = bytes([0x08, 00, 0x81, port_id, 0x11, 0x51, 0x00, p & 0xFF])
        await client.write_gatt_char(HUB_CHAR_UUID, data, response=False)

    bridge = Bridge(name, write, has_light=cfg["has_light"])
    await bridge.stop_motor()
    report_status(name, "online")
    print(f"   [OK] {name} ({mac}) connected, motor stopped.")
    return client, bridge


async def main():
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    last_cmds = {}
    clients = {}
    bridges = {}

    print("Connecting to available LEGO hubs (press green button on any hubs you want to use)...")
    for cfg in TRAIN_CONFIGS:
        client, bridge = await connect_hub(cfg, last_cmds)
        if client and bridge:
            clients[cfg["mac"]] = client
            bridges[cfg["mac"]] = bridge

    if not bridges:
        print("No LEGO hubs connected. Turn on at least one hub and run again.")
        return

    print(f"\nActive trains connected: {len(bridges)}/{len(TRAIN_CONFIGS)}")

    mq = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(c, userdata, flags, reason_code, properties=None):
        print(f"MQTT connected ({reason_code}); listening on {COMMAND_TOPIC}")
        c.subscribe(COMMAND_TOPIC)

    def on_message(c, userdata, msg):
        loop.call_soon_threadsafe(
            queue.put_nowait,
            ("msg", msg.payload.decode(errors="replace"), time.perf_counter()))

    def on_disconnect(c, userdata, flags, reason_code, properties=None):
        loop.call_soon_threadsafe(queue.put_nowait, ("mqtt_down",))

    mq.on_connect, mq.on_message, mq.on_disconnect = on_connect, on_message, on_disconnect
    mq.connect(BROKER_HOST, BROKER_PORT, keepalive=10)
    mq.loop_start()

    try:
        last_heartbeat = time.monotonic()

        while any(c.is_connected for c in clients.values()):
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
                last_heartbeat = time.monotonic()
            except asyncio.TimeoutError:
                if time.monotonic() - last_heartbeat > 5.0:
                    running = [b for b in bridges.values() if b.power != 0]
                    if running:
                        print("!! WATCHDOG TIMEOUT: Upstream connection lost (Backend/Rocrail). "
                              "Halting all trains.")
                        for b in running:
                            await b.stop_motor()
                continue

            if item[0] == "mqtt_down":
                print("!! MQTT broker connection lost: stopping all trains")
                for b in bridges.values():
                    await b.stop_motor()
                continue

            _, payload, t_rx = item
            action = interpret(payload)
            if action is None:
                continue

            if action["kind"] == "note":
                print(f"   ({action['text']})")
            elif action["kind"] == "stop_all":
                print(f"STOP ALL ({action['why']})")
                for b in bridges.values():
                    await b.stop_motor()
            elif action["kind"] == "loco":
                mac = action["mac"]
                bridge = bridges.get(mac)
                if bridge is None:
                    continue
                if action["warn"]:
                    print(f"   warning: {action['warn']}")
                direction = "forward" if action["forward"] else "reverse"
                print(f"[{action['name']}] speed {action['v']:.0f}, {direction}, "
                      f"light {'on' if action['light'] else 'off'}"
                      f" -> motor power {action['power']}")
                await bridge.apply_loco(action["power"], action["light"])
                t_done = time.perf_counter()
                last_cmds[mac] = {
                    "t_done": t_done,
                    "rx_to_write_ms": (t_done - t_rx) * 1000,
                    "v": action["v"],
                    "power": action["power"],
                }
        print("!! All Bluetooth links lost.")
    finally:
        print("Shutting down: stopping all motors...")
        mq.loop_stop()
        for mac, b in bridges.items():
            report_status(b.name, "offline")
            try:
                await b.shutdown()
            except Exception as exc:
                print(f"(could not send final stop to {b.name}: {exc})")
        await asyncio.sleep(0.3)
        for c in clients.values():
            try:
                if c.is_connected:
                    await c.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)