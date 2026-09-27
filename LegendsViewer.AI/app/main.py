from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from app.agent import stream_chat
from app.config import get_settings
from app.schemas import ChatRequest

# Ensure app.* INFO logs show up under uvicorn/docker (uvicorn only wires its own loggers).
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    _app_logger.addHandler(_handler)
    _app_logger.setLevel(logging.INFO)
    _app_logger.propagate = False

settings = get_settings()

app = FastAPI(title="LegendsViewer AI", version="0.1.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == ["*"] else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.openai_model}


@app.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    async def event_generator():
        async for item in stream_chat(request.message, request.history):
            yield {
                "event": item["event"],
                "data": json.dumps(item["data"], ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
