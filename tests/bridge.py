"""
bridge.py: Rocrail (MQTT) -> LEGO Powered Up hub 88009 (Bluetooth LE)

Rocrail stays the authority. This program only translates: it listens on
Rocrail's MQTT command topic and turns loco commands into motor power for
the hub. Your FastAPI backend does not change at all.

Setup:
    py -m pip install bleak paho-mqtt
Before running:
    - Mosquitto running, Rocrail's MQTT controller configured
    - hub switched on (green button, LED blinking), LEGO app closed
    - hub_test.py closed (a hub accepts only one connection)
Run:
    py bridge.py
Stop with Ctrl+C (the train is stopped before exit).
"""

import asyncio
import csv
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import paho.mqtt.client as mqtt
from bleak import BleakClient

# ---------------- settings you can change ----------------
BROKER_HOST = "localhost"
BROKER_PORT = 1883
COMMAND_TOPIC = "rocrail/service/command"   # Rocrail -> hardware (seen in your recording)

HUB_ADDRESS = "9C:9A:C0:4A:8B:B9"           # your hub, found by hub_test.py
LOCO_ADDR = "1"                             # Rocrail loco address 1 = this hub
MOTOR_PORT = 0x00                           # port A
LIGHT_PORT = 0x01                           # port B (lights)

MIN_POWER = 22        # lowest power that reliably moves the train (you measured 18-20)
TOP_POWER = 40        # power at Rocrail speed 100%. Only raise after testing on curves!
LIGHT_POWER = 40      # brightness used when F0 is on
DIRECTION_SIGN = 1    # set to -1 if "forward" drives the train backwards
REVERSE_PAUSE = 0.6   # seconds to wait at standstill when direction flips while moving
STOP_ON_POWER_OFF = False   # see notes: turn on after checking what Rocrail sends
LOG_FILE = "latency_log.csv"

HUB_CHAR_UUID = "00001624-1212-efde-1623-785feabcd123"
# ---------------------------------------------------------


def speed_to_power(v: float, v_max: float) -> int:
    """Rocrail speed (0..V_max) -> motor power. 0 stays 0; anything above starts at MIN_POWER."""
    if v <= 0 or v_max <= 0:
        return 0
    fraction = min(v / v_max, 1.0)
    return round(MIN_POWER + fraction * (TOP_POWER - MIN_POWER))


def interpret(payload: str):
    """Turn one Rocrail XML message into an action dict, or None to ignore it."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None

    if root.tag == "lc":
        if root.get("addr") != LOCO_ADDR:
            return None
        try:
            v = float(root.get("V", "0"))
            v_max = float(root.get("V_max", "100"))
        except ValueError:
            return None
        forward = root.get("dir", "true") == "true"
        power = speed_to_power(v, v_max) * (1 if forward else -1) * DIRECTION_SIGN
        light = root.get("f0", root.get("fn", "false")) == "true"
        return {
            "kind": "loco", "power": power, "light": light, "v": v, "forward": forward,
            "warn": None if root.get("V_mode", "percent") == "percent"
            else f"V_mode is {root.get('V_mode')}, expected percent",
        }

    if root.tag == "sys":
        cmd = root.get("cmd")
        if cmd in ("stop", "ebreak"):          # assumption: Rocrail's stop buttons use these
            return {"kind": "stop_all", "why": f"sys cmd={cmd}"}
        return {"kind": "note", "text": f"sys message: {payload[:120]}"}

    if root.tag == "state":
        if root.get("power") == "false" and STOP_ON_POWER_OFF:
            return {"kind": "stop_all", "why": "power off"}
        return {"kind": "note", "text": f"state message: power={root.get('power')}"}

    return None  # clock, boosterlist, fbinfo, other locos ... ignored


class Bridge:
    """Holds what we last told the hub, and applies changes safely."""

    def __init__(self, write):
        self._write = write          # async function(port_id, power)
        self.power = 0
        self.light = False

    async def apply_loco(self, power: int, light: bool):
        if power != self.power:
            reversing = self.power != 0 and power != 0 and (power > 0) != (self.power > 0)
            if reversing:
                print("   direction flipped while moving: stopping first")
                await self._write(MOTOR_PORT, 0)
                self.power = 0
                await asyncio.sleep(REVERSE_PAUSE)
            await self._write(MOTOR_PORT, power)
            self.power = power
        if light != self.light:
            await self._write(LIGHT_PORT, LIGHT_POWER if light else 0)
            self.light = light

    async def stop_motor(self):
        """Always sends the stop, even if we think the motor is already stopped."""
        await self._write(MOTOR_PORT, 0)
        self.power = 0

    async def shutdown(self):
        await self.stop_motor()
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


async def main():
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    last_cmd = {}   # timing of the most recent motor command, for the latency log

    def on_notify(_, data: bytearray):
        # 0x82 = Port Output Command Feedback: the hub acknowledging a port command
        if len(data) >= 4 and data[2] == 0x82 and data[3] == MOTOR_PORT and last_cmd:
            ack_ms = (time.perf_counter() - last_cmd["t_done"]) * 1000
            log_latency(last_cmd["rx_to_write_ms"], ack_ms, last_cmd["v"], last_cmd["power"])
            print(f"   latency: MQTT->BLE write {last_cmd['rx_to_write_ms']:.0f} ms, "
                  f"write->hub ack {ack_ms:.0f} ms")
            last_cmd.clear()

    print(f"Connecting to hub {HUB_ADDRESS} (hub on, LED blinking, LEGO app closed)...")
    async with BleakClient(HUB_ADDRESS) as client:
        await client.start_notify(HUB_CHAR_UUID, on_notify)

        async def write(port_id: int, power: int):
            power = max(-TOP_POWER, min(TOP_POWER, power)) if port_id == MOTOR_PORT else power
            data = bytes([0x08, 0x00, 0x81, port_id, 0x11, 0x51, 0x00, power & 0xFF])
            await client.write_gatt_char(HUB_CHAR_UUID, data, response=False)

        bridge = Bridge(write)
        await bridge.stop_motor()    # start from a known state
        print("Hub connected, motor stopped.")

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

            while client.is_connected:
                try:
                    # Check the queue frequently enough to run the watchdog promptly.
                    item = await asyncio.wait_for(queue.get(), timeout=0.5)
                    last_heartbeat = time.monotonic()
                except asyncio.TimeoutError:
                    if bridge.power != 0 and time.monotonic() - last_heartbeat > 5.0:
                        print("!! WATCHDOG TIMEOUT: Upstream connection lost (Backend/Rocrail). "
                              "Halting train.")
                        await bridge.stop_motor()
                    continue

                if item[0] == "mqtt_down":
                    print("!! MQTT broker connection lost: stopping the train")
                    await bridge.stop_motor()
                    continue

                _, payload, t_rx = item
                action = interpret(payload)
                if action is None:
                    continue

                if action["kind"] == "note":
                    print(f"   ({action['text']})")
                elif action["kind"] == "stop_all":
                    print(f"STOP ALL ({action['why']})")
                    await bridge.stop_motor()
                elif action["kind"] == "loco":
                    if action["warn"]:
                        print(f"   warning: {action['warn']}")
                    direction = "forward" if action["forward"] else "reverse"
                    print(f"Rocrail: speed {action['v']:.0f}, {direction}, "
                          f"light {'on' if action['light'] else 'off'}"
                          f" -> motor power {action['power']}")
                    t0 = time.perf_counter()
                    await bridge.apply_loco(action["power"], action["light"])
                    t_done = time.perf_counter()
                    last_cmd.update(t_done=t_done, rx_to_write_ms=(t_done - t_rx) * 1000,
                                    v=action["v"], power=action["power"])
            print("!! Bluetooth link to the hub was lost (the hub stops itself on a clean link loss)")
        finally:
            print("Shutting down: stopping the motor...")
            mq.loop_stop()
            try:
                await bridge.shutdown()
                await asyncio.sleep(0.3)
            except Exception as exc:
                print(f"(could not send final stop: {exc})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)