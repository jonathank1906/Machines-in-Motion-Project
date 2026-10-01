"""Fire each command at the virtual layout, watch Rocview react.
Usage (from project root): python -m tools.try_commands BR103 sw1
"""
import asyncio
import sys
import traceback

from backend.rocrail_adapter import RocrailAdapter


async def main(loco, sw):
    print(f"Starting command test: loco={loco} switch={sw}", flush=True)
    a = RocrailAdapter()
    await a.connect()
    await asyncio.sleep(2)
    print(f"Rocrail status: {a.state['status']}", flush=True)

    async def step(label, coro, wait=3):
        print(f">> {label}", flush=True)
        try:
            await coro
        except Exception:
            print("   FAILED:", flush=True)
            traceback.print_exc()
            return
        await asyncio.sleep(wait)
        print("   loco:", a.state["locomotives"].get(loco), flush=True)
        print("   switch:", a.state["switches"].get(sw), flush=True)

    await step("speed 30", a.set_speed(loco, 30))
    await step("speed 999 (cap should reduce it)", a.set_speed(loco, 999))
    await step("direction reverse", a.set_direction(loco, False), 4)
    await step("speed 30", a.set_speed(loco, 30))
    await step("stop", a.stop(loco))
    await step("switch flip", a.throw_switch(sw))
    await step("switch flip again", a.throw_switch(sw))
    a.disconnect()
    print("Done.", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m tools.try_commands <loco_id> <switch_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))