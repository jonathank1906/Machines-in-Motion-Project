"""Step 1: run while Rocrail (Virtual mode) drives a loco automatically.
Writes every frame that is NOT a plain lc/sw event to captured_frames.txt, plus a tag count summary.
Run from project root:  python -m tools.capture_frames   (Ctrl+C to stop; ~2-3 minutes is plenty)"""
import asyncio, collections, re
from backend.rocrail_adapter import RocrailAdapter

counts = collections.Counter()
out = open("captured_frames.txt", "a", encoding="utf-8")


class Capture(RocrailAdapter):
    def _handle_frame(self, name, body):
        text = body.decode("utf-8", errors="replace").strip("\x00 \r\n\t")
        tags = re.findall(r"<(\w+)[\s/>]", text)
        top = tags[0] if tags else "?"
        counts[top] += 1
        if top not in ("lc", "sw") or counts[top] <= 3:   # first few of each, plus everything else
            out.write(f"--- name={name} top={top}\n{text[:1500]}\n")
            out.flush()
        super()._handle_frame(name, body)


async def main():
    a = Capture(log_frames=False)
    await a.connect()
    try:
        while True:
            await asyncio.sleep(10)
            print(dict(counts), flush=True)
    finally:
        a.disconnect()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("final counts:", dict(counts))