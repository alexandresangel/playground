"""Existing scoped session endpoints and storage contracts."""

from __future__ import annotations
from dia_jwt.fastapi import Identity
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pascal.api.schemas import SessionCreateResponse, SessionDetailResponse, SessionListResponse, SessionSummary
from pascal.runtime import Runtime, _session_store_error
from session_store import turns_for_client
from typing import Dict

CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"


def create_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()
    get_identity = runtime.get_identity

    @router.get("/api/sessions", response_model=SessionListResponse)
    def list_sessions_endpoint(
        identity: Identity = Depends(get_identity),
    ) -> SessionListResponse:
        try:
            rows = runtime.sessions.list_sessions(identity.scope_path)
        except RuntimeError as exc:
            raise _session_store_error(exc) from exc
        sessions = [
            SessionSummary(
                session_id=str(row.get("session_id", "")),
                title=str(row.get("title", "")),
                created_at=str(row.get("created_at", "")),
                updated_at=str(row.get("updated_at", "")),
                has_response=bool(row.get("has_response")),
            )
            for row in rows
            if row.get("session_id")
        ]
        return SessionListResponse(sessions=sessions)

    @router.post("/api/sessions", response_model=SessionCreateResponse)
    def create_session_endpoint(
        identity: Identity = Depends(get_identity),
    ) -> SessionCreateResponse:
        try:
            record = runtime.sessions.create_session(identity.scope_path)
        except RuntimeError as exc:
            raise _session_store_error(exc) from exc
        return SessionCreateResponse(
            session_id=str(record["session_id"]),
            created_at=str(record["created_at"]),
        )

    @router.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    def get_session_endpoint(
        session_id: str,
        identity: Identity = Depends(get_identity),
    ) -> SessionDetailResponse:
        record = runtime.sessions.get_session(session_id, identity.scope_path)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown session_id")
        turns = record.get("turns", [])
        if not isinstance(turns, list):
            turns = []
        payload = SessionDetailResponse(
            session_id=session_id,
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
            turns=turns_for_client(turns),
        )
        return JSONResponse(
            content=payload.model_dump(),
            headers={CHAT_SESSION_HEADER: session_id},
        )

    @router.delete("/api/sessions/{session_id}")
    def delete_session_endpoint(
        session_id: str,
        identity: Identity = Depends(get_identity),
    ) -> Dict[str, bool]:
        scope = identity.scope_path
        try:
            if runtime.sessions.get_session(session_id, scope) is None:
                raise HTTPException(status_code=404, detail="Unknown session_id")
            if not runtime.sessions.delete_session(session_id, scope):
                raise HTTPException(status_code=404, detail="Unknown session_id")
        except RuntimeError as exc:
            raise _session_store_error(exc) from exc
        return {"ok": True}

    return router
