"""The ONE module that talks to an LLM (CONTRACTS 1).

`LLMClient` wraps one or more OpenAI-compatible Chat Completions providers (OpenCode Go, Voke, custom)
through the `openai` SDK with tool calling, retries, timeouts, a per-provider model fallback list and
provider-to-provider fallback (connect error, 5xx, 401/403, 429, timeout). `FakeLLM` is the
deterministic, scripted stand-in used by tests and by the scripted planner that records shippable
replays. API keys are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from zill import config

log = logging.getLogger("zill.agent.llm")

PROBE_TIMEOUT_S = 4.0
CALL_TIMEOUT_S = 30.0
AVAIL_CACHE_S = 60.0
RETRIES = 2
RATE_WAIT_MAX_S = float(os.environ.get("ZILL_LLM_RATE_WAIT_MAX_S", "45"))  # longest wait, all throttled
RATE_WAITS = 4  # waits before giving up when every model stays rate-limited
COOLDOWN_S = 30.0
USER_AGENT = "Zill-hackathon-prototype/0.1"
_THINK = re.compile(r"<think>.*?</think>", re.S)


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
    provider: str = ""
    reasoning: str = ""


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
    """The assistant turn to append to `messages` after a ChatResult (keeps tool_call ids).

    `reasoning_content` is kept (thinking models such as Kimi want it echoed back with tool calls); the
    client strips it again for providers that do not take it.
    """
    msg: dict[str, Any] = {"role": "assistant", "content": res.content or ""}
    if res.reasoning:
        msg["reasoning_content"] = res.reasoning
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


class _EmptyResponse(Exception):
    pass


def _status_of(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _retry_after(exc: BaseException) -> float:
    """Seconds from a 429's Retry-After header (default 5)."""
    resp = getattr(exc, "response", None)
    raw = getattr(resp, "headers", {}).get("retry-after") if resp is not None else None
    try:
        return max(0.5, float(raw)) if raw is not None else 5.0
    except (TypeError, ValueError):
        return 5.0


def classify(exc: BaseException) -> str:
    """auth | rate | notfound | bad | empty | transient (name-based so SDK versions do not matter)."""
    kind, code = type(exc).__name__, _status_of(exc)
    if kind in ("AuthenticationError", "PermissionDeniedError") or code in (401, 403):
        return "auth"
    if kind == "RateLimitError" or code == 429:
        return "rate"
    if kind == "NotFoundError" or code == 404:
        return "notfound"
    if kind == "_EmptyResponse":
        return "empty"
    if kind == "BadRequestError" or code in (400, 422):
        return "bad"
    return "transient"  # connect errors, timeouts, 5xx, anything unknown


def _describe(exc: BaseException | None) -> str:
    """Error summary safe to log: class name and HTTP status only (messages may echo credentials)."""
    if exc is None:
        return "unknown"
    code = _status_of(exc)
    return type(exc).__name__ + (f" {code}" if code else "")


class _Endpoint:
    """One provider: base URL, key, models, headers and its own availability cache / cooldown."""

    def __init__(
        self,
        name: str,
        base_url: str,
        key: str,
        model: str,
        fast_model: str,
        fallbacks: list[str] | None = None,
        models_url: str | None = None,
        session_header: bool = False,
        keep_reasoning: bool = False,
        client: Any = None,
    ) -> None:
        self.name, self.base_url, self.key = name, base_url, key
        self.model, self.fast_model = model, fast_model
        self.fallbacks = fallbacks
        self.models_url = models_url
        self.session_header = session_header
        self.keep_reasoning = keep_reasoning
        self.client = client
        self.avail: tuple[float, bool, str] | None = None
        self.chosen_model: str | None = None
        self.reason = ""
        self.cooldown_until = 0.0

    def headers(self, session_id: str) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT}
        if self.session_header:
            h["x-opencode-session"] = session_id
        return h

    def fallback_models(self, listed: list[str] | None = None) -> list[str]:
        if self.fallbacks is not None:
            order = [self.model, *self.fallbacks]
        else:
            order = [self.model, "claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
        if listed:
            order.append(listed[0])
        seen: list[str] = []
        for m in order:
            if m and m not in seen:
                seen.append(m)
        return seen

    def sdk(self, timeout: float, session_id: str) -> Any:
        if self.client is not None:
            return self.client
        from openai import OpenAI

        return OpenAI(
            base_url=self.base_url,
            api_key=self.key,
            timeout=timeout,
            max_retries=0,
            default_headers=self.headers(session_id),
        )


def configured_endpoints() -> list[_Endpoint]:
    """Endpoints from `config` in `ZILL_LLM_PROVIDERS` order; providers without a key are skipped."""
    out: list[_Endpoint] = []
    for name in config.LLM_PROVIDERS:
        n = name.strip().lower()
        if n == "opencode" and config.OPENCODE_API_KEY:
            out.append(
                _Endpoint(
                    "opencode",
                    config.OPENCODE_BASE_URL,
                    config.OPENCODE_API_KEY,
                    config.OPENCODE_MODEL,
                    config.OPENCODE_MODEL_FAST,
                    fallbacks=list(config.OPENCODE_FALLBACK_MODELS),
                    models_url=config.OPENCODE_MODELS_URL,
                    session_header=True,
                    keep_reasoning=True,
                )
            )
        elif n in ("voke", "custom") and config.VOKE_API_KEY:
            out.append(
                _Endpoint(
                    n,
                    config.VOKE_BASE_URL,
                    config.VOKE_API_KEY,
                    config.VOKE_MODEL,
                    config.VOKE_MODEL_FAST,
                    fallbacks=list(config.VOKE_FALLBACK_MODELS) if config.VOKE_FALLBACK_MODELS else None,
                )
            )
    return out


class LLMClient:
    """Provider chain. `LLMClient()` builds it from config; passing base_url/api_key/client/model makes
    a single-provider client (tests, scripts)."""

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
        endpoints: list[_Endpoint] | None = None,
        session_id: str | None = None,
    ) -> None:
        single = any(x is not None for x in (base_url, api_key, client, model, fast_model))
        if endpoints is not None:
            self.endpoints = endpoints
        elif single:
            self.endpoints = [
                _Endpoint(
                    "voke",
                    base_url or config.VOKE_BASE_URL,
                    api_key if api_key is not None else config.VOKE_API_KEY,
                    model or config.VOKE_MODEL,
                    fast_model or config.VOKE_MODEL_FAST,
                    client=client,
                )
            ]
        else:
            self.endpoints = configured_endpoints()
        self._sleep = sleep
        self._clock = clock
        self.session_id = session_id or f"zill-{uuid.uuid4().hex[:16]}"
        self.reason = ""

    # ---- compatibility surface (single-provider callers/tests) ----------------------------------
    @property
    def _primary(self) -> _Endpoint | None:
        return self.endpoints[0] if self.endpoints else None

    @property
    def model(self) -> str:
        return self._primary.model if self._primary else config.MODEL

    @property
    def chosen_model(self) -> str | None:
        for ep in self.endpoints:
            if ep.avail and ep.avail[1]:
                return ep.chosen_model
        return self._primary.chosen_model if self._primary else None

    @property
    def base_url(self) -> str:
        return self._primary.base_url if self._primary else ""

    def fallback_models(self, listed: list[str] | None = None) -> list[str]:
        return self._primary.fallback_models(listed) if self._primary else []

    def for_session(self, session_id: str) -> LLMClient:
        """A view sharing endpoints (and their caches) but sending its own `x-opencode-session`."""
        return LLMClient(
            endpoints=self.endpoints, sleep=self._sleep, clock=self._clock, session_id=session_id
        )

    # ---- health -----------------------------------------------------------------------------
    def _probe(self, ep: _Endpoint) -> bool:
        now = self._clock()
        if ep.avail and now - ep.avail[0] < AVAIL_CACHE_S:
            return ep.avail[1]
        ok, reason = False, ""
        if not ep.key:
            reason = "no API key"
        else:
            try:
                if ep.models_url and ep.client is None:
                    import httpx

                    r = httpx.get(
                        ep.models_url,
                        headers={**ep.headers(self.session_id), "Authorization": f"Bearer {ep.key}"},
                        timeout=PROBE_TIMEOUT_S,
                    )
                    r.raise_for_status()
                    listed = [m["id"] for m in r.json().get("data", [])]
                else:
                    listed = [m.id for m in ep.sdk(PROBE_TIMEOUT_S, self.session_id).models.list()]
                ok = True
                ep.chosen_model = next((m for m in ep.fallback_models() if m in listed), None) or (
                    listed[0] if listed else ep.model
                )
            except Exception as exc:  # network, auth, timeout...
                reason = type(exc).__name__
                code = _status_of(exc) or getattr(getattr(exc, "response", None), "status_code", None)
                if code:
                    reason += f" {code}"
        ep.reason = reason
        ep.avail = (now, ok, reason)
        return ok

    def available(self) -> bool:
        """Some provider has a key AND answers its model list within 4 s. Cached 60 s per provider."""
        if not self.endpoints:
            self.reason = "no API key"
            return False
        ok = False
        for ep in self.endpoints:
            ok = self._probe(ep) or ok
        self.reason = "" if ok else "; ".join(f"{e.name}: {e.reason}" for e in self.endpoints)
        return ok

    def status(self) -> dict[str, Any]:
        ok = self.available()
        live = next((e for e in self.endpoints if e.avail and e.avail[1]), None)
        prim = live or self._primary
        return {
            "available": ok,
            "model": (prim.chosen_model or prim.model) if prim else config.MODEL,
            "provider": prim.name if prim else None,
            "providers": [
                {
                    "name": e.name,
                    "available": bool(e.avail and e.avail[1]),
                    "model": e.chosen_model or e.model,
                    "reason": e.reason,
                }
                for e in self.endpoints
            ],
            "reason": self.reason,
        }

    # ---- chat -------------------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        session_id: str | None = None,
    ) -> ChatResult:
        """`tools` is [{name, description, parameters}] (converted here).

        Walks providers in priority order (skipping ones in cooldown unless all are); within a provider
        walks its model list. Transient errors retry x2 with backoff only on the last provider.
        `model="fast"` selects each provider's fast model.
        """
        if not self.endpoints:
            raise LLMError("LLM call failed (no provider configured)")
        sid = session_id or self.session_id
        now = self._clock()
        order = [e for e in self.endpoints if e.cooldown_until <= now] or list(self.endpoints)
        fails: list[str] = []
        for i, ep in enumerate(order):
            retries = RETRIES if i == len(order) - 1 else 0
            try:
                return self._chat_endpoint(ep, messages, tools, model, temperature, sid, retries)
            except LLMError as exc:
                fails.append(str(exc))  # already key-safe: provider, kind, exception class + status
                ep.cooldown_until = self._clock() + COOLDOWN_S
                log.warning("llm provider failed: %s", exc)
        raise LLMError("LLM call failed (" + "; ".join(fails) + ")") from None

    def _chat_endpoint(
        self,
        ep: _Endpoint,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        temperature: float,
        sid: str,
        retries: int,
    ) -> ChatResult:
        if model == "fast":
            model = ep.fast_model
        candidates = [model] if model else [ep.chosen_model or ep.model]
        candidates += [m for m in ep.fallback_models() if m not in candidates]
        last: BaseException | None = None
        throttled: list[float] = []  # Retry-After of each model that answered 429
        for mdl in candidates:
            attempt = 0
            use_tool_choice = True
            while True:
                try:
                    return self._once(ep, mdl, messages, tools, temperature, sid, use_tool_choice)
                except Exception as exc:
                    last = exc
                    kind = classify(exc)
                    if kind == "bad" and tools and use_tool_choice:
                        use_tool_choice = False  # provider rejects tool_choice: retry once without it
                        continue
                    if kind == "rate":
                        throttled.append(_retry_after(exc))
                        break  # per-model token buckets (e.g. Groq): try the next model
                    if kind in ("notfound", "empty", "bad") and not model:
                        break  # next model in this provider's list
                    if kind != "transient":
                        raise LLMError(f"{ep.name}: {kind} ({_describe(exc)})") from None
                    if attempt >= retries:
                        break
                    attempt += 1
                    self._sleep(0.6 * (2**attempt))
            if last is not None and classify(last) == "rate":
                if retries:
                    continue  # last provider: walk its models (separate per-model buckets)
                break  # a later provider can take the call
            if model or (last is not None and classify(last) in ("transient", "auth")):
                break  # provider down: do not walk its whole model list
        if retries and throttled and len(throttled) == len(candidates):
            # every model is throttled: wait once for the soonest bucket (bounded), then retry it
            wait = min(throttled)
            best = candidates[throttled.index(wait)]
            for _ in range(RATE_WAITS):
                if wait > RATE_WAIT_MAX_S:
                    break
                self._sleep(wait)
                try:
                    return self._once(ep, best, messages, tools, temperature, sid, True)
                except Exception as exc:
                    last = exc
                    if classify(exc) != "rate":
                        break
                    wait = _retry_after(exc)
        if last is not None and classify(last) in ("auth", "rate"):
            raise LLMError(f"{ep.name}: {classify(last)} ({_describe(last)})") from None
        raise LLMError(f"{ep.name}: call failed ({_describe(last)})") from None

    def _once(
        self,
        ep: _Endpoint,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        sid: str,
        use_tool_choice: bool,
    ) -> ChatResult:
        if not ep.keep_reasoning:
            messages = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
            if use_tool_choice:
                kwargs["tool_choice"] = "auto"
        resp = ep.sdk(CALL_TIMEOUT_S, sid).chat.completions.create(
            timeout=CALL_TIMEOUT_S, extra_headers=ep.headers(sid), **kwargs
        )
        choice = resp.choices[0]
        msg = choice.message
        calls: list[ToolCall] = []
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or []):
            fn = tc.function
            args, err = parse_tool_args(getattr(fn, "arguments", None))
            calls.append(ToolCall(id=tc.id or f"call_{i}", name=fn.name, arguments=args, arguments_error=err))
        content = _THINK.sub("", _content_text(getattr(msg, "content", None))).strip()
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
        if not content and not calls:
            raise _EmptyResponse("empty completion")  # reasoning-only or blank: try the next model
        usage = getattr(resp, "usage", None)
        return ChatResult(
            content=content,
            tool_calls=calls,
            model=getattr(resp, "model", model) or model,
            finish_reason=getattr(choice, "finish_reason", "") or "",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
            provider=ep.name,
            reasoning=reasoning if isinstance(reasoning, str) else "",
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

    def for_session(self, session_id: str) -> FakeLLM:
        return self

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        session_id: str | None = None,
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
    """Agent status for /api/health (never touches the network, never includes a key).

    mode: "live" when a provider key is configured and ZILL_REPLAY is off (reachability is checked
    lazily by LLMClient.available() at session creation), otherwise "replay". Recordings are classed
    by their `live` flag: live ones are "recorded", the rest "scripted". `providers` lists the
    configured (keyed) providers in priority order with their models; `provider`/`model` are the first.
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
    eps = configured_endpoints()
    live = bool(eps) and not config.REPLAY
    return {
        "mode": "live" if live else "replay",
        "key_present": bool(eps),
        "provider": eps[0].name if eps else None,
        "model": eps[0].model if eps else None,
        "providers": [{"name": e.name, "model": e.model, "fast_model": e.fast_model} for e in eps],
        "replay_available": bool(names),
        "recordings": len(names),
        "recordings_live": live_n,
        "recordings_scripted": scripted_n,
        "recorded_sessions": names,
        "recording_kind": "recorded" if names and not scripted_n else ("scripted" if names else "none"),
    }
