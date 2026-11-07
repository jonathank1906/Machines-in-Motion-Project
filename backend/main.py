from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os
import asyncio

from backend.rocrail_adapter import RocrailAdapter
from backend.commands import EStopActive
from backend.plan_parser import parse_plan
from backend import config

adapter = RocrailAdapter()
layout = parse_plan(adapter.plan_file) 


async def heartbeat_loop():
    while True:
        try:
            await adapter.send_command('<clock cmd="get"/>', 'clock')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[heartbeat] Rocrail pulse failed: {exc}", flush=True)
        await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await adapter.connect()
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        yield
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        adapter.disconnect()

app = FastAPI(lifespan=lifespan)

frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))


@app.get("/api/state")
async def get_state():
    return {**adapter.get_state(), "estop": adapter.estop_active}


@app.get("/api/layout")
async def get_layout():
    return layout


@app.get("/api/allowed")
async def get_allowed():
    return {"locos": sorted(config.ALLOWED_LOCOS),
            "switches": sorted(config.ALLOWED_SWITCHES),
            "max_speed": config.MAX_SPEED}


def _guard(exc):
    if isinstance(exc, EStopActive):
        return exc
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    return HTTPException(502, f"Rocrail unreachable: {exc}")


async def _do(coro):
    try:
        return await coro
    except EStopActive:
        raise
    except Exception as e:
        raise _guard(e)


@app.exception_handler(EStopActive)
async def estop_active_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.post("/api/loco/{loco_id}/speed/{speed}")
async def set_speed(loco_id: str, speed: int):
    applied = await _do(adapter.set_speed(loco_id, speed))
    return {"status": "success", "loco_id": loco_id, "speed": applied}


@app.post("/api/loco/{loco_id}/direction/{direction}")
async def set_direction(loco_id: str, direction: str):
    if direction not in ("forward", "reverse"):
        raise HTTPException(400, "direction must be forward or reverse")
    await _do(adapter.set_direction(loco_id, direction == "forward"))
    return {"status": "success", "loco_id": loco_id, "direction": direction}


@app.post("/api/loco/{loco_id}/stop")
async def stop_loco(loco_id: str):
    await _do(adapter.stop(loco_id))
    return {"status": "success", "loco_id": loco_id, "action": "stop"}


@app.post("/api/estop")
async def estop():
    await _do(adapter.emergency_stop_all())
    return {"status": "success", "action": "emergency_stop"}


@app.post("/api/estop/reset")
async def estop_reset():
    await adapter.reset_estop()
    return {"ok": True}


@app.post("/api/switch/{sw_id}/{position}")
async def throw_switch(sw_id: str, position: str = "flip"):
    await _do(adapter.throw_switch(sw_id, position))
    return {"status": "success", "switch": sw_id, "position": position}

@app.post("/api/loco/{loco_id}/light/{state}")
async def set_light(loco_id: str, state: str):
    if state not in ("true", "false"):
        raise HTTPException(400, "light state must be true or false")
    await _do(adapter.set_light(loco_id, state == "true"))
    return {"status": "success", "loco_id": loco_id, "light_on": state == "true"}