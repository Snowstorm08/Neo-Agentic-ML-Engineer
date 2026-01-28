"""
FastAPI entrypoint wiring the ChatKit server and REST endpoints.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from chatkit.server import StreamingResult

from .chat import FactAssistantServer, create_chatkit_server
from .facts import fact_store


# =========================
# App Setup
# =========================

app = FastAPI(
    title="ChatKit API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# =========================
# ChatKit Dependency
# =========================

_chatkit_server: FactAssistantServer | None = None


@app.on_event("startup")
async def startup() -> None:
    global _chatkit_server
    _chatkit_server = create_chatkit_server()


def get_chatkit_server() -> FactAssistantServer:
    if _chatkit_server is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ChatKit dependencies are missing. "
                "Install the ChatKit Python package to enable this endpoint."
            ),
        )
    return _chatkit_server


# =========================
# Chat Endpoint
# =========================

@app.post(
    "/chatkit",
    summary="Chat with the assistant",
    response_class=Response,
)
async def chatkit_endpoint(
    request: Request,
    server: FactAssistantServer = Depends(get_chatkit_server),
) -> Response:
    payload = await request.body()
    result = await server.process(payload, context={"request": request})

    if isinstance(result, StreamingResult):
        return StreamingResponse(
            result,
            media_type="text/event-stream",
        )

    if hasattr(result, "json"):
        return Response(
            content=result.json,
            media_type="application/json",
        )

    return JSONResponse(content=result)


# =========================
# Facts API
# =========================

@app.get(
    "/facts",
    summary="List saved facts",
)
async def list_facts() -> Dict[str, Any]:
    facts = await fact_store.list_saved()
    return {
        "facts": [fact.as_dict() for fact in facts]
    }


@app.post(
    "/facts/{fact_id}/save",
    summary="Save a fact",
)
async def save_fact(fact_id: str) -> Dict[str, Any]:
    fact = await fact_store.mark_saved(fact_id)
    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fact not found",
        )
    return {"fact": fact.as_dict()}


@app.post(
    "/facts/{fact_id}/discard",
    summary="Discard a fact",
)
async def discard_fact(fact_id: str) -> Dict[str, Any]:
    fact = await fact_store.discard(fact_id)
    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fact not found",
        )
    return {"fact": fact.as_dict()}


# =========================
# Health Check
# =========================

@app.get(
    "/health",
    summary="Health check",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
