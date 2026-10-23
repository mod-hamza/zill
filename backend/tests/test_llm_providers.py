"""Provider chain (OpenCode Go + Voke) against local stub HTTP servers using the real `openai` SDK."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from zill import config
from zill.agent import llm as llm_mod
from zill.agent.llm import LLMClient, LLMError, _Endpoint, configured_endpoints

SECRET_A = "sk-opencode-SECRET-123"
SECRET_B = "sk-voke-SECRET-456"


class Stub:
    """Scriptable OpenAI-compatible server. `plan` entries: (status, body_dict) popped per chat request."""

    def __init__(self, plan=None, models=("m1",)):
        self.plan = list(plan or [])
        self.models = list(models)
        self.requests: list[dict] = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _send(self, status, obj):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                data = [{"id": m, "object": "model"} for m in stub.models]
                self._send(200, {"object": "list", "data": data})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append({"headers": dict(self.headers.items()), "body": body, "path": self.path})
                status, obj = stub.plan.pop(0) if stub.plan else (200, ok("default"))
                self._send(status, obj)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def ok(text="", tool_calls=None, reasoning=None, model="m1"):
    msg: dict = {"role": "assistant", "content": text}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    if reasoning:
        msg["reasoning_content"] = reasoning
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


def err(msg="boom"):
    return {"error": {"message": msg, "type": "x"}}


@pytest.fixture
def stubs():
    made: list[Stub] = []

    def make(*a, **kw):
        s = Stub(*a, **kw)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def chain(a: Stub, b: Stub | None = None, **kw) -> LLMClient:
    eps = [
        _Endpoint("opencode", a.url, SECRET_A, "kimi-k3", "glm-5.3-flash",
                  fallbacks=["glm-5.3"], session_header=True, keep_reasoning=True)
    ]
    if b is not None:
        eps.append(_Endpoint("voke", b.url, SECRET_B, "claude-sonnet-5-5", "claude-haiku-5-5"))
    return LLMClient(endpoints=eps, sleep=lambda s: None, **kw)


MSG = [{"role": "user", "content": "hi"}]


def test_primary_used_and_headers_sent(stubs):
    a, b = stubs([(200, ok("from a"))]), stubs()
    c = chain(a, b, session_id="sess-42")
    res = c.chat(MSG)
    assert res.content == "from a" and res.provider == "opencode"
    h = {k.lower(): v for k, v in a.requests[0]["headers"].items()}
    assert h["x-opencode-session"] == "sess-42"
    assert h["user-agent"] == "Zill-hackathon-prototype/0.1"
    assert h["authorization"] == f"Bearer {SECRET_A}"
    assert not b.requests


def test_session_header_only_for_opencode(stubs):
    a, b = stubs([(500, err())]), stubs([(200, ok("from b"))])
    c = chain(a, b)
    assert c.chat(MSG).provider == "voke"
    hb = {k.lower() for k in b.requests[0]["headers"]}
    assert "x-opencode-session" not in hb


def test_for_session_changes_header(stubs):
    a = stubs([(200, ok("x"))])
    c = chain(a).for_session("conv-7")
    c.chat(MSG)
    assert {k.lower(): v for k, v in a.requests[0]["headers"].items()}["x-opencode-session"] == "conv-7"


@pytest.mark.parametrize("status", [429, 401, 403, 500, 503])
def test_failure_falls_to_next_provider(stubs, status):
    a, b = stubs([(status, err())] * 6), stubs([(200, ok("from b"))])
    res = chain(a, b).chat(MSG)
    assert res.content == "from b" and res.provider == "voke"
    assert len(a.requests) == 1  # no retry storm on a non-last provider (nor a model walk)


def test_connect_error_falls_to_next(stubs):
    b = stubs([(200, ok("from b"))])
    dead = Stub()
    dead.close()  # port closed -> connection refused
    c = LLMClient(
        endpoints=[
            _Endpoint("opencode", dead.url, SECRET_A, "kimi-k3", "f", session_header=True),
            _Endpoint("voke", b.url, SECRET_B, "claude-sonnet-5-5", "h"),
        ],
        sleep=lambda s: None,
    )
    assert c.chat(MSG).provider == "voke"


def test_model_fallback_within_provider(stubs):
    a = stubs([(404, err("no such model")), (200, ok("glm", model="glm-5.3"))])
    res = chain(a).chat(MSG)
    assert [r["body"]["model"] for r in a.requests] == ["kimi-k3", "glm-5.3"]
    assert res.content == "glm"


def test_all_fail_raises_without_secrets(stubs, caplog):
    a, b = stubs([(401, err(f"bad key {SECRET_A}"))] * 3), stubs([(429, err(f"slow {SECRET_B}"))] * 3)
    c = chain(a, b)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LLMError) as ei:
            c.chat(MSG)
    blob = str(ei.value) + caplog.text + repr(ei.value.__cause__)
    assert SECRET_A not in blob and SECRET_B not in blob


def test_key_never_logged_on_success(stubs, caplog):
    a = stubs([(200, ok("fine"))])
    with caplog.at_level(logging.DEBUG):
        chain(a).chat(MSG)
        chain(a).status()
    assert SECRET_A not in caplog.text


def test_cooldown_skips_failed_provider(stubs):
    t = [0.0]
    a, b = stubs([(500, err())]), stubs([(200, ok("1")), (200, ok("2"))])
    c = chain(a, b, clock=lambda: t[0])
    c.chat(MSG)
    c.chat(MSG)  # a is cooling: not asked again
    assert len(a.requests) == 1 and len(b.requests) == 2
    t[0] = 31
    a.plan.append((200, ok("a back")))
    assert c.chat(MSG).provider == "opencode"


def test_retry_without_tool_choice_when_rejected(stubs):
    a = stubs([(400, err("tool_choice not supported")), (200, ok("done"))])
    tools = [{"name": "t", "description": "d", "parameters": {"type": "object"}}]
    res = chain(a).chat(MSG, tools=tools)
    assert res.content == "done"
    assert a.requests[0]["body"].get("tool_choice") == "auto"
    assert "tool_choice" not in a.requests[1]["body"] and a.requests[1]["body"]["tools"]


def test_tool_args_as_string_and_reasoning_content(stubs):
    fn = {"name": "get_sun", "arguments": '{"at": "13:00"}'}
    calls = [{"id": "c1", "type": "function", "function": fn}]
    a = stubs([(200, ok("", calls, reasoning="thinking..."))])
    spec = {"name": "get_sun", "description": "d", "parameters": {"type": "object"}}
    res = chain(a).chat(MSG, tools=[spec])
    assert res.tool_calls[0].arguments == {"at": "13:00"} and res.reasoning == "thinking..."
    assert llm_mod.assistant_message(res)["reasoning_content"] == "thinking..."


def test_empty_content_with_reasoning_tries_next_model(stubs):
    a = stubs([(200, ok("", reasoning="only thoughts")), (200, ok("real answer"))])
    res = chain(a).chat(MSG)
    assert res.content == "real answer" and len(a.requests) == 2


def test_think_tags_stripped(stubs):
    a = stubs([(200, ok("<think>hmm</think>Answer."))])
    assert chain(a).chat(MSG).content == "Answer."


def test_reasoning_content_stripped_for_other_providers(stubs):
    b = stubs([(200, ok("ok"))])
    c = chain(stubs(), b)
    c.endpoints = c.endpoints[1:]
    c.chat([{"role": "assistant", "content": "x", "reasoning_content": "r"}, *MSG])
    assert "reasoning_content" not in b.requests[0]["body"]["messages"][0]


def test_fast_alias(stubs):
    a = stubs([(200, ok("quick"))])
    chain(a).chat(MSG, model="fast")
    assert a.requests[0]["body"]["model"] == "glm-5.3-flash"


def test_available_probe_and_status(stubs):
    a, b = stubs(models=["kimi-k3"]), stubs(models=["claude-sonnet-5-5"])
    c = chain(a, b)
    assert c.available()
    st = c.status()
    assert st["provider"] == "opencode" and st["model"] == "kimi-k3"
    assert [p["name"] for p in st["providers"]] == ["opencode", "voke"]
    assert SECRET_A not in json.dumps(st) and SECRET_B not in json.dumps(st)


# ---- config wiring --------------------------------------------------------------------------------
def _cfg(monkeypatch, **kw):
    base = dict(
        LLM_PROVIDERS=["opencode", "voke"], OPENCODE_API_KEY="", VOKE_API_KEY="",
        OPENCODE_MODEL="kimi-k3", OPENCODE_MODEL_FAST="glm-5.3-flash",
        OPENCODE_BASE_URL="https://opencode.ai/inference/go/openai/v1",
        OPENCODE_MODELS_URL="https://opencode.ai/inference/go/v1/models",
        OPENCODE_FALLBACK_MODELS=["glm-5.3"], VOKE_BASE_URL="https://www.vokeapi.com/v1",
        VOKE_MODEL="claude-sonnet-5-5", VOKE_MODEL_FAST="claude-haiku-5-5",
    )
    base.update(kw)
    for k, v in base.items():
        monkeypatch.setattr(config, k, v)


def test_no_keys_means_no_endpoints_and_unavailable(monkeypatch):
    _cfg(monkeypatch)
    assert configured_endpoints() == []
    c = LLMClient()
    assert c.available() is False and c.reason == "no API key"
    with pytest.raises(LLMError):
        c.chat(MSG)
    st = llm_mod.status()
    assert st["mode"] == "replay" and st["key_present"] is False and st["provider"] is None


def test_priority_order_from_env(monkeypatch):
    _cfg(monkeypatch, OPENCODE_API_KEY=SECRET_A, VOKE_API_KEY=SECRET_B)
    assert [e.name for e in configured_endpoints()] == ["opencode", "voke"]
    _cfg(monkeypatch, OPENCODE_API_KEY=SECRET_A, VOKE_API_KEY=SECRET_B, LLM_PROVIDERS=["voke", "opencode"])
    assert [e.name for e in configured_endpoints()] == ["voke", "opencode"]
    ep = configured_endpoints()[1]
    assert ep.base_url.endswith("/inference/go/openai/v1") and ep.model == "kimi-k3" and ep.session_header


def test_only_voke_key_is_legacy_behaviour(monkeypatch):
    _cfg(monkeypatch, VOKE_API_KEY=SECRET_B)
    assert [e.name for e in configured_endpoints()] == ["voke"]
    st = llm_mod.status()
    assert st["mode"] == "live" and st["provider"] == "voke" and SECRET_B not in json.dumps(st)


def test_status_never_contains_key(monkeypatch):
    _cfg(monkeypatch, OPENCODE_API_KEY=SECRET_A, VOKE_API_KEY=SECRET_B)
    blob = json.dumps(llm_mod.status())
    assert SECRET_A not in blob and SECRET_B not in blob


def test_replay_flag_forces_replay_mode(monkeypatch):
    _cfg(monkeypatch, OPENCODE_API_KEY=SECRET_A)
    monkeypatch.setattr(config, "REPLAY", True)
    assert llm_mod.status()["mode"] == "replay"
