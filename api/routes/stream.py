from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from orchestration.pipeline import PipelineRunner

router = APIRouter(tags=["stream"])


def _sse_format(event: dict) -> str:
    payload = json.dumps(event, default=str)
    return f"data: {payload}\n\n"


@router.post("/query/stream")
async def stream_query(request: Request) -> StreamingResponse:
    """Stream orchestration events for a single query via SSE.

    Expects JSON body: {"query": "..."}
    Streams incremental small JSON events with event-type semantics.
    """
    body = await request.json()
    query = body.get("query", "")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def event_sink(event: dict) -> None:
        await queue.put(event)

    async def generator() -> AsyncGenerator[str, None]:
        # Start by yielding a ready event
        await queue.put({"event_type": "stream_started", "query": query})

        # Run pipeline in background
        async def runner_task():
            runner = PipelineRunner()
            try:
                await runner.run(query, event_sink=event_sink)
            except Exception as exc:
                await queue.put({"event_type": "pipeline_error", "error": str(exc)})
            finally:
                await queue.put({"event_type": "stream_complete"})

        task = asyncio.create_task(runner_task())

        # Stream events until complete
        while True:
            event = await queue.get()
            yield _sse_format(event)
            if event.get("event_type") == "stream_complete":
                break

        # ensure runner task is done
        await task

    return StreamingResponse(generator(), media_type="text/event-stream")
