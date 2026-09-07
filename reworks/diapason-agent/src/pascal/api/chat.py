"""Legacy JSON and SSE wire contracts, backed by the same ChatService."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from pascal.agent.service import BusyError
from pascal.i18n import locale_from_header_value

SESSION_HEADER = "X-Diapason-Chat-Session"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    client_timezone: str | None = None


def router(deps: dict) -> APIRouter:
    api = APIRouter()

    async def prepare(body, request, identity, streaming):
        try:
            return await request.app.state.chat.open(
                identity=identity,
                message=body.message,
                session_id=body.session_id or request.headers.get(SESSION_HEADER),
                locale=locale_from_header_value(request.headers.get("X-Diapason-Locale")),
                timezone=body.client_timezone,
                streaming=streaming,
            )
        except KeyError as exc:
            raise HTTPException(404, "Unknown session_id") from exc
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, "Agent preparation unavailable") from exc

    @api.post("/api/chat")
    async def chat(body: ChatRequest, request: Request, identity=Depends(deps["get_identity"])):
        handle = await prepare(body, request, identity, False)
        try:
            await asyncio.shield(handle.task)
        except asyncio.CancelledError:
            await handle.disconnect()
            raise
        payload = handle.payload(request.app.state.config.get("azure_openai", {}))
        return JSONResponse(
            payload,
            status_code=200 if handle.outcome.persisted else 503,
            headers={SESSION_HEADER: handle.session_id},
        )

    @api.post("/api/chat/stream")
    async def stream(body: ChatRequest, request: Request, identity=Depends(deps["get_identity"])):
        handle = await prepare(body, request, identity, True)

        async def events():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(handle.queue.get(), timeout=15)
                    except TimeoutError:
                        if handle.task.done():
                            # No silent hanging SSE if an unexpected producer failure occurs.
                            yield 'data: {"type":"error","content":"Stream interrupted"}\n\n'
                            break
                        yield ": keepalive\n\n"
                        continue
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    if event["type"] == "done":
                        yield "data: [DONE]\n\n"
                        break
            finally:
                await handle.disconnect()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                SESSION_HEADER: handle.session_id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return api
