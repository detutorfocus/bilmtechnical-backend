"""
Live Chat — Real WebSocket implementation

HONEST SCOPE NOTE: this is a genuine real-time chat, not a static widget.
It uses in-memory storage for message history and active connections,
which means:
  - Chat history is LOST on API container restart. Fine for an MVP/launch,
    but if you need persistent chat logs later, this needs a ChatMessage
    DB table instead of the in-memory dict below. Flagging this now so
    it's a deliberate choice, not a surprise later.
  - This works correctly with a SINGLE API container. If you ever scale
    to multiple API replicas behind a load balancer, WebSocket connections
    on different replicas can't see each other's messages without adding
    Redis pub/sub as a message bus. Not needed at your current scale —
    just flagging the ceiling honestly.

ARCHITECTURE:
  Visitor connects  -> ws://.../api/chat/ws/visitor/{visitor_id}
  Admin connects     -> ws://.../api/chat/ws/admin/{token}
  Messages relay through an in-memory ConnectionManager to whichever
  admin is currently connected; if no admin is online, messages queue
  in history and the visitor sees "waiting for a response".
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.config import settings

router = APIRouter(prefix="/chat", tags=["Live Chat"])


class ConnectionManager:
    """
    In-memory chat state. See module docstring for the honest scaling
    caveats — this is correct and sufficient for a single-instance deploy.
    """
    def __init__(self):
        self.visitor_sockets: Dict[str, WebSocket] = {}
        self.admin_sockets: List[WebSocket] = []
        self.history: Dict[str, List[dict]] = {}  # visitor_id -> [messages]

    async def connect_visitor(self, visitor_id: str, ws: WebSocket):
        await ws.accept()
        self.visitor_sockets[visitor_id] = ws
        self.history.setdefault(visitor_id, [])
        # Send existing history so a page refresh doesn't lose context
        await ws.send_json({"type": "history", "messages": self.history[visitor_id]})
        # Notify any connected admins that a new visitor is online
        for admin_ws in self.admin_sockets:
            await admin_ws.send_json({"type": "visitor_connected", "visitor_id": visitor_id})

    def disconnect_visitor(self, visitor_id: str):
        self.visitor_sockets.pop(visitor_id, None)

    async def connect_admin(self, ws: WebSocket):
        await ws.accept()
        self.admin_sockets.append(ws)
        await ws.send_json({
            "type": "active_visitors",
            "visitors": [
                {"visitor_id": vid, "message_count": len(msgs)}
                for vid, msgs in self.history.items()
                if vid in self.visitor_sockets
            ],
        })

    def disconnect_admin(self, ws: WebSocket):
        if ws in self.admin_sockets:
            self.admin_sockets.remove(ws)

    async def visitor_send(self, visitor_id: str, text: str, sender_name: str = "Visitor"):
        msg = {"type": "message", "from": "visitor", "sender": sender_name, "text": text, "timestamp": datetime.utcnow().isoformat(), "visitor_id": visitor_id}
        self.history.setdefault(visitor_id, []).append(msg)
        # Echo back to the visitor (confirms send) and relay to all connected admins
        if visitor_id in self.visitor_sockets:
            await self.visitor_sockets[visitor_id].send_json({**msg, "from": "visitor_echo"})
        for admin_ws in self.admin_sockets:
            await admin_ws.send_json(msg)

    async def admin_send(self, visitor_id: str, text: str, admin_name: str = "Support"):
        msg = {"type": "message", "from": "admin", "sender": admin_name, "text": text, "timestamp": datetime.utcnow().isoformat(), "visitor_id": visitor_id}
        self.history.setdefault(visitor_id, []).append(msg)
        if visitor_id in self.visitor_sockets:
            await self.visitor_sockets[visitor_id].send_json(msg)
        for admin_ws in self.admin_sockets:
            await admin_ws.send_json({**msg, "from": "admin_echo"})


manager = ConnectionManager()


@router.websocket("/ws/visitor/{visitor_id}")
async def visitor_ws(websocket: WebSocket, visitor_id: str):
    await manager.connect_visitor(visitor_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            await manager.visitor_send(visitor_id, data.get("text", ""), data.get("sender", "Visitor"))
    except WebSocketDisconnect:
        manager.disconnect_visitor(visitor_id)
        for admin_ws in manager.admin_sockets:
            try:
                await admin_ws.send_json({"type": "visitor_disconnected", "visitor_id": visitor_id})
            except Exception:
                pass


@router.websocket("/ws/admin/{token}")
async def admin_ws(websocket: WebSocket, token: str):
    """
    Admin auth for the WebSocket: since WS connections can't send
    Authorization headers easily from a browser, the JWT is passed as
    a path parameter instead. Validated the same way as normal HTTP auth.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if not payload.get("sub"):
            await websocket.close(code=4001)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    await manager.connect_admin(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            await manager.admin_send(data["visitor_id"], data.get("text", ""), data.get("sender", "Support"))
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


@router.get("/history/{visitor_id}")
async def get_chat_history(visitor_id: str):
    """REST fallback to fetch history without opening a WebSocket (e.g. for debugging)."""
    return {"visitor_id": visitor_id, "messages": manager.history.get(visitor_id, [])}


@router.get("/active-visitors")
async def get_active_visitors():
    return {
        "visitors": [
            {"visitor_id": vid, "message_count": len(msgs)}
            for vid, msgs in manager.history.items()
            if vid in manager.visitor_sockets
        ]
    }
