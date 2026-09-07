"""Existing scoped Blob API; synchronous storage stays off the event loop."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from pascal.api.chat import SESSION_HEADER
from pascal.sessions.blob_store import turns_for_client


def router(deps: dict) -> APIRouter:
    api = APIRouter()

    async def call(request, method, *args):
        try:
            return await asyncio.to_thread(getattr(request.app.state.store, method), *args)
        except Exception as exc:
            raise HTTPException(503, "Session storage unavailable") from exc

    @api.get("/api/sessions")
    async def sessions(request: Request, identity=Depends(deps["get_identity"])):
        return {"sessions": await call(request, "list_sessions", identity.scope_path)}

    @api.post("/api/sessions")
    async def create(request: Request, identity=Depends(deps["get_identity"])):
        record = await call(request, "create_session", identity.scope_path)
        return {"session_id": record["session_id"], "created_at": record["created_at"]}

    @api.get("/api/sessions/{session_id}")
    async def detail(session_id: str, request: Request, identity=Depends(deps["get_identity"])):
        record = await call(request, "get_session", session_id, identity.scope_path)
        if record is None:
            raise HTTPException(404, "Unknown session_id")
        return JSONResponse(
            {key: record[key] for key in ("session_id", "created_at", "updated_at")}
            | {
                "turns": turns_for_client(record.get("turns", [])),
            },
            headers={SESSION_HEADER: session_id},
        )

    @api.delete("/api/sessions/{session_id}")
    async def delete(session_id: str, request: Request, identity=Depends(deps["get_identity"])):
        if (identity.scope_path, session_id) in request.app.state.chat.active:
            raise HTTPException(409, "Session has an active turn")
        if not await call(request, "delete_session", session_id, identity.scope_path):
            raise HTTPException(404, "Unknown session_id")
        return {"ok": True}

    return api
