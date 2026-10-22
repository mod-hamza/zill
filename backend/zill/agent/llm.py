"""The ONE module that talks to an LLM (CONTRACTS 1).

`LLMClient` wraps an OpenAI-compatible Chat Completions endpoint (Voke) through the `openai` SDK
with tool calling, retries, timeouts and a model fallback list. `FakeLLM` is the deterministic,
scripted stand-in used by tests and by the scripted planner that records shippable replays.
The API key is never logged.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from zill import config

log = logging.getLogger("zill.agent.llm")

PROBE_TIMEOUT_S = 4.0
CALL_TIMEOUT_S = 30.0
AVAIL_CACHE_S = 60.0
RETRIES = 2


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    arguments_error: str | None = None


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)


def to_openai_tools(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{name, description, parameters}] -> OpenAI `tools` payload."""
    return [
        {
            "type": "function",
            "function": {"name": s["name"], "description": s["description"], "parameters": s["parameters"]},
        }
        for s in specs
    ]


def assistant_message(res: ChatResult) -> dict[str, Any]:
    """The assistant turn to append to `messages` after a ChatResult (keeps tool_call ids)."""
    msg: dict[str, Any] = {"role": "assistant", "content": res.content or ""}
    if res.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in res.tool_calls
        ]
    return msg


def parse_tool_args(raw: Any) -> tuple[dict[str, Any], str | None]:
    """Providers differ: arguments may be a JSON string, a dict, fenced, or empty."""
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        s = raw.strip()
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
        try:
            val = json.loads(s)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", s, re.S)
            if m:
                try:
                    val = json.loads(m.group(0))
                except json.JSONDecodeError:
                    return {}, f"unparseable tool arguments: {s[:80]}"
            else:
                return {}, f"unparseable tool arguments: {s[:80]}"
        if isinstance(val, str):  # double-encoded
            return parse_tool_args(val)
        if isinstance(val, dict):
            return val, None
        return {}, "tool arguments were not an object"
    return {}, "tool arguments had an unsupported type"


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


class LLMClient:
    scripted = False

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        fast_model: str | None = None,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url or config.LLM_BASE_URL
        self._key = api_key if api_key is not None else config.LLM_API_KEY
        self.model = model or config.MODEL
        self.fast_model = fast_model or config.MODEL_FAST
        self._client = client  # injected (tests) or lazily built
        self._sleep = sleep
        self._clock = clock
        self._avail: tuple[float, bool, str] | None = None
        self.chosen_model: str | None = None
        self.reason = ""

    # ---- plumbing ---------------------------------------------------------------------------
    def _sdk(self, timeout: float) -> Any:
        if self._client is not None:
            return self._client
        from openai import OpenAI

        return OpenAI(base_url=self.base_url, api_key=self._key, timeout=timeout, max_retries=0)

    def fallback_models(self, listed: list[str] | None = None) -> list[str]:
        order = [self.model, "claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
        if listed:
            order.append(listed[0])
        seen: list[str] = []
        for m in order:
            if m and m not in seen:
                seen.append(m)
        return seen

    # ---- health -----------------------------------------------------------------------------
    def available(self) -> bool:
        """Key present AND GET /models answers within 4 s. Cached 60 s."""
        now = self._clock()
        if self._avail and now - self._avail[0] < AVAIL_CACHE_S:
            return self._avail[1]
        ok, reason = False, ""
        if not self._key:
            reason = "no API key"
        else:
            try:
                listed = [m.id for m in self._sdk(PROBE_TIMEOUT_S).models.list()]
                ok = True
                self.chosen_model = next((m for m in self.fallback_models() if m in listed), None) or (
                    listed[0] if listed else self.model
                )
            except Exception as exc:  # network, auth, timeout...
                reason = f"{type(exc).__name__}"
        self.reason = reason
        self._avail = (now, ok, reason)
        return ok

    def status(self) -> dict[str, Any]:
        ok = self.available()
        return {"available": ok, "model": self.chosen_model or self.model, "reason": self.reason}

    # ---- chat -------------------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """`tools` is [{name, description, parameters}] (converted here). Retries x2 with backoff."""
        candidates = [model] if model else [self.chosen_model or self.model]
        if not model:
            candidates += [m for m in self.fallback_models() if m not in candidates]
        last: Exception | None = None
        for mdl in candidates:
            attempt = 0
            while True:
                try:
                    return self._once(mdl, messages, tools, temperature)
                except Exception as exc:
                    last = exc
                    kind = type(exc).__name__
                    if kind in ("NotFoundError",) and not model:
                        break  # try next model in the fallback list
                    if kind in ("AuthenticationError", "PermissionDeniedError", "BadRequestError"):
                        raise LLMError(f"{kind}: request rejected") from exc
                    if attempt >= RETRIES:
                        break
                    attempt += 1
                    self._sleep(0.6 * (2**attempt))
            if model:
                break
        raise LLMError(f"LLM call failed ({type(last).__name__ if last else 'unknown'})") from last

    def _once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"
        resp = self._sdk(CALL_TIMEOUT_S).chat.completions.create(timeout=CALL_TIMEOUT_S, **kwargs)
        choice = resp.choices[0]
        msg = choice.message
        calls: list[ToolCall] = []
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or []):
            fn = tc.function
            args, err = parse_tool_args(getattr(fn, "arguments", None))
            calls.append(ToolCall(id=tc.id or f"call_{i}", name=fn.name, arguments=args, arguments_error=err))
        usage = getattr(resp, "usage", None)
        return ChatResult(
            content=_content_text(getattr(msg, "content", "")),
            tool_calls=calls,
            model=getattr(resp, "model", model) or model,
            finish_reason=getattr(choice, "finish_reason", "") or "",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        )


# ------------------------------------------------------------------------------------------------
# Deterministic stand-in
# ------------------------------------------------------------------------------------------------
Scripted = ChatResult | str | Callable[[list[dict[str, Any]], list[dict[str, Any]] | None], ChatResult]


def tool_call(name: str, args: dict[str, Any], id: str | None = None) -> ToolCall:
    return ToolCall(id=id or f"call_{name}", name=name, arguments=args)


class FakeLLM:
    """Plays back a script: each `chat` pops the next ChatResult / str / callable."""

    scripted = False

    def __init__(self, script: list[Scripted] | None = None, model: str = "fake-llm") -> None:
        self.script = list(script or [])
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def available(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {"available": True, "model": self.model, "reason": "fake"}

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self.script:
            raise LLMError("FakeLLM script exhausted")
        nxt = self.script.pop(0)
        if callable(nxt):
            nxt = nxt(messages, tools)
        if isinstance(nxt, str):
            nxt = ChatResult(content=nxt, model=self.model)
        if not nxt.model:
            nxt.model = self.model
        return nxt


def status() -> dict[str, Any]:
    """Agent status for /api/health (never touches the network).

    mode: "live" when a key is configured and ZILL_REPLAY is off (reachability is checked lazily by
    LLMClient.available() at session creation), otherwise "replay". Recordings are classed by their
    `live` flag: live ones are "recorded", the rest "scripted".
    """
    import json as _json

    names: list[str] = []
    live_n = scripted_n = 0
    d = config.REPLAY_DIR
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            try:
                rec = _json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            names.append(rec.get("scenario_id", f.stem))
            if rec.get("live"):
                live_n += 1
            else:
                scripted_n += 1
    live = bool(config.LLM_API_KEY) and not config.REPLAY
    return {
        "mode": "live" if live else "replay",
        "key_present": bool(config.LLM_API_KEY),
        "replay_available": bool(names),
        "recordings": len(names),
        "recordings_live": live_n,
        "recordings_scripted": scripted_n,
        "recorded_sessions": names,
        "recording_kind": "recorded" if names and not scripted_n else ("scripted" if names else "none"),
    }
