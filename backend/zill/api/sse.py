"""Server-Sent Events helpers (shared with the agent stream).

Wire format: `event: <name>\\ndata: <json>\\n\\n`.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from typing import Any

import orjson
from fastapi.responses import StreamingResponse

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format one SSE message. `data` is JSON-encoded on a single line."""
    payload = orjson.dumps(
        data,
        option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS,
        default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o),
    ).decode()
    return f"event: {event}\ndata: {payload}\n\n"


def sse_response(gen: AsyncIterator[str] | Iterator[str] | Iterable[str]) -> StreamingResponse:
    """Wrap a generator of already-formatted SSE strings in a StreamingResponse."""
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)


async def run_in_thread_sse(
    work: Callable[[Callable[[str, dict[str, Any]], None]], Any],
    *,
    done_event: str = "done",
    error_event: str = "error",
) -> AsyncIterator[str]:
    """Run blocking `work(emit)` in a thread; yield SSE strings for each emit(event, data).

    The return value of `work` (a dict) is sent as the final `done_event`; exceptions as `error_event`.
    """
    q: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

    def emit(event: str, data: dict[str, Any]) -> None:
        q.put((event, data))

    def runner() -> None:
        try:
            res = work(emit)
            q.put((done_event, res if isinstance(res, dict) else {"result": res}))
        except Exception as e:  # typed, no stack trace to the client
            q.put((error_event, {"code": "task_failed", "message": str(e)}))
        finally:
            q.put(None)

    threading.Thread(target=runner, daemon=True).start()
    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            return
        yield sse_event(*item)
