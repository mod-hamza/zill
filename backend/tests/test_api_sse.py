"""SSE helper tests (shared with the agent stream)."""

from __future__ import annotations

import asyncio
import json

from zill.api.sse import run_in_thread_sse, sse_event


def test_sse_event_format():
    s = sse_event("agent", {"id": 1, "payload": {"a": [1, 2]}})
    assert s.startswith("event: agent\ndata: ") and s.endswith("\n\n")
    assert "\n" not in s[len("event: agent\n") : -2].replace("data: ", "", 1)
    assert json.loads(s.split("data: ", 1)[1]) == {"id": 1, "payload": {"a": [1, 2]}}


def test_run_in_thread_sse_progress_done_and_error():
    async def collect(work):
        return [x async for x in run_in_thread_sse(work)]

    def ok(emit):
        emit("progress", {"n": 1})
        return {"fine": True}

    out = asyncio.run(collect(ok))
    assert [e.split("\n")[0] for e in out] == ["event: progress", "event: done"]

    def bad(emit):
        raise RuntimeError("boom")

    out = asyncio.run(collect(bad))
    assert out[-1].startswith("event: error") and "Traceback" not in out[-1]
