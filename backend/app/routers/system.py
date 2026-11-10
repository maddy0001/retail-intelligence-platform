"""Health check and the WebSocket endpoint the React app keeps open."""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..db import get_db
from ..security import user_from_token
from ..services.realtime import manager

router = APIRouter(tags=["system"])
state = {"change_stream": None}


@router.get("/api/health")
def health(db=Depends(get_db)):
    hello = db.command("hello")
    worker = state["change_stream"]
    return {"status": "ok", "database": db.name, "replica_set": hello.get("setName"),
            "change_stream": bool(worker and worker.is_alive() and worker.ready.is_set())}


@router.websocket("/ws")
async def websocket(ws: WebSocket, token: str = ""):
    user = user_from_token(get_db(), token) if token else None
    if user is None:
        await ws.close(code=4401)
        return
    await manager.connect(ws, user)
    try:
        await ws.send_json({"type": "hello", "role": user.get("role")})
        while True:
            await ws.receive_text()   # the client only sends keep-alive pings
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, user)
