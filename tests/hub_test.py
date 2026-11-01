"""
Step 1: talk to a LEGO Powered Up hub (88009 City Hub) over Bluetooth LE.
No Rocrail, no MQTT. Just: find the hub, connect, listen, spin the motor.

Setup:
    pip install bleak
Run:
    python hub_test.py

Commands once connected (type then press Enter):
    a 20     run port A at +20% power
    b -20    run port B at -20% power (reverse)
    stop     stop both ports
    quit     stop both ports and disconnect
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

# From LEGO's published Wireless Protocol 3.0
HUB_SERVICE_UUID = "00001623-1212-efde-1623-785feabcd123"
HUB_CHAR_UUID = "00001624-1212-efde-1623-785feabcd123"
LEGO_COMPANY_ID = 0x0397

PORTS = {"a": 0x00, "b": 0x01}
MAX_POWER = 40  # safety cap for first tests; raise it later on purpose


def power_command(port_id: int, power: int) -> bytes:
    """Port Output Command (0x81), StartPower via WriteDirectModeData (0x51).
    Example from LEGO's spec: 08 00 81 00 11 51 00 32 = port A at 50%."""
    power = max(-MAX_POWER, min(MAX_POWER, power))
    return bytes([0x08, 0x00, 0x81, port_id, 0x11, 0x51, 0x00, power & 0xFF])


def on_notify(_, data: bytearray):
    print(f"[hub -> laptop] {data.hex(' ')}")
    # Message type 0x04 = Hub Attached I/O: tells us what is plugged into which port
    if len(data) >= 5 and data[2] == 0x04:
        port = data[3]
        event = {0: "detached", 1: "attached", 2: "attached (virtual)"}.get(data[4], "?")
        io_type = int.from_bytes(data[5:7], "little") if len(data) >= 7 else None
        print(f"    port {port}: {event}, device type id {io_type}")


async def find_hub():
    print("Scanning for 10 seconds. Press the hub's green button so its LED blinks...")
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    hubs = []
    for address, (device, adv) in found.items():
        uuids = [u.lower() for u in adv.service_uuids]
        if HUB_SERVICE_UUID in uuids or LEGO_COMPANY_ID in adv.manufacturer_data:
            hubs.append((device, adv))
    if not hubs:
        print("No LEGO hub found. Other Bluetooth devices seen nearby:")
        for address, (device, adv) in found.items():
            if device.name:
                print(f"  {device.name}  ({address})")
        return None
    device, adv = hubs[0]
    print(f"Found hub: {device.name or 'unnamed'}  ({device.address}), signal {adv.rssi} dBm")
    return device


async def stop_all(client):
    if client.is_connected:
        for port_id in PORTS.values():
            try:
                await client.write_gatt_char(HUB_CHAR_UUID, power_command(port_id, 0), response=False)
            except Exception as exc:
                print(f"(stop failed: {exc})")


async def main():
    device = await find_hub()
    if device is None:
        return

    def on_disconnect(_):
        print("!! Hub disconnected (the train stops when the hub loses power or link)")

    async with BleakClient(device, disconnected_callback=on_disconnect) as client:
        print("Connected. Listening for hub messages...")
        await client.start_notify(HUB_CHAR_UUID, on_notify)
        await asyncio.sleep(2)  # let the 'attached I/O' messages arrive
        print(__doc__.split("Commands once connected")[1].split('"""')[0])

        loop = asyncio.get_running_loop()
        try:
            while client.is_connected:
                line = (await loop.run_in_executor(None, input, "> ")).strip().lower()
                if line in ("quit", "q", "exit"):
                    break
                if line in ("stop", "s", ""):
                    await stop_all(client)
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[0] in PORTS:
                    try:
                        power = int(parts[1])
                    except ValueError:
                        print("Power must be a whole number, e.g. a 20")
                        continue
                    data = power_command(PORTS[parts[0]], power)
                    print(f"[laptop -> hub] {data.hex(' ')}")
                    await client.write_gatt_char(HUB_CHAR_UUID, data, response=False)
                else:
                    print("Unknown command. Try: a 20 | b -20 | stop | quit")
        finally:
            print("Stopping motors before exit...")
            await stop_all(client)
            await asyncio.sleep(0.3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted. If the train is still moving, type stop or press the hub button.")
        sys.exit(0)