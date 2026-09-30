from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from backend.rocrail_adapter import RocrailAdapter

adapter = RocrailAdapter()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Await the native async connection directly
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