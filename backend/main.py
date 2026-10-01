from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from backend.rocrail_adapter import RocrailAdapter

adapter = RocrailAdapter()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await adapter.connect()
    yield
    adapter.disconnect()

app = FastAPI(lifespan=lifespan)

frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/api/state")
async def get_state():
    return adapter.get_state()

# NEW: Endpoint to set locomotive speed
@app.post("/api/loco/{loco_id}/speed/{speed}")
async def set_speed(loco_id: str, speed: int):
    # Construct the exact XML command Rocrail expects
    body = f'<lc id="{loco_id}" V="{speed}" cmd="velocity"/>'
    await adapter.send_command(body, 'lc')
    return {"status": "success", "loco_id": loco_id, "speed": speed}

# NEW: Endpoint to emergency stop a locomotive
@app.post("/api/loco/{loco_id}/stop")
async def stop_loco(loco_id: str):
    body = f'<lc id="{loco_id}" V="0" cmd="stop"/>'
    await adapter.send_command(body, 'lc')
    return {"status": "success", "loco_id": loco_id, "action": "stop"}