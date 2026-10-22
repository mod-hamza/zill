"""LLMClient against a fake OpenAI-compatible server (monkeypatched SDK client)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from zill.agent.llm import ChatResult, FakeLLM, LLMClient, LLMError, assistant_message, parse_tool_args


class FakeSDK:
    """Mimics the parts of openai.OpenAI that LLMClient uses."""

    def __init__(self, models=("claude-sonnet-5-5",), responses=None, fail_times=0, fail_exc=None):
        self.listed = list(models)
        self.responses = list(responses or [])
        self.fail_times = fail_times
        self.fail_exc = fail_exc or ConnectionError("boom")
        self.calls: list[dict] = []
        self.models = NS(list=lambda: [NS(id=m) for m in self.listed])
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.fail_exc
        return self.responses.pop(0)


def resp(content="", tool_calls=None, model="claude-sonnet-5-5"):
    msg = NS(content=content, tool_calls=tool_calls)
    return NS(
        choices=[NS(message=msg, finish_reason="stop")],
        model=model,
        usage=NS(prompt_tokens=10, completion_tokens=5),
    )


def tc(id_, name, args):
    return NS(id=id_, function=NS(name=name, arguments=args))


def client(sdk, key="k", **kw):
    return LLMClient(base_url="http://fake/v1", api_key=key, client=sdk, sleep=lambda s: None, **kw)


def test_no_key_not_available():
    c = client(FakeSDK(), key="")
    assert c.available() is False and "no API key" in c.reason


def test_available_probes_models_and_caches():
    t = [0.0]
    sdk = FakeSDK()
    n = {"calls": 0}
    orig = sdk.models.list

    def counted():
        n["calls"] += 1
        return orig()

    sdk.models = NS(list=counted)
    c = LLMClient(base_url="x", api_key="k", client=sdk, clock=lambda: t[0])
    assert c.available() and c.available()
    assert n["calls"] == 1  # cached within 60 s
    t[0] = 61
    c.available()
    assert n["calls"] == 2
    assert c.status()["model"] == "claude-sonnet-5-5"


def test_unreachable_models_endpoint():
    sdk = FakeSDK()
    sdk.models = NS(list=lambda: (_ for _ in ()).throw(TimeoutError("slow")))
    assert client(sdk).available() is False


def test_model_fallback_chain():
    c = client(FakeSDK(models=["claude-haiku-5-5", "other"]), model="my-custom-model")
    assert c.available()
    assert c.chosen_model == "claude-haiku-5-5"
    assert c.fallback_models(["zzz"])[:2] == ["my-custom-model", "claude-sonnet-5-5"]
    assert c.fallback_models(["zzz"])[-1] == "zzz"


def test_tool_calls_parsed_incl_string_args_and_fenced_json():
    sdk = FakeSDK(
        responses=[
            resp(
                "thinking",
                [
                    tc("c1", "compare_routes", '{"origin": "metro", "dest": "opera"}'),
                    tc("c2", "get_sun", {"at": "13:30"}),
                    tc("c3", "get_weather", '```json\n{"at": "14:00"}\n```'),
                    tc("c4", "bad", "{not json"),
                    tc("c5", "empty", ""),
                ],
            )
        ]
    )
    out = client(sdk).chat(
        [{"role": "user", "content": "x"}],
        tools=[{"name": "compare_routes", "description": "d", "parameters": {"type": "object"}}],
    )
    assert [t.name for t in out.tool_calls] == ["compare_routes", "get_sun", "get_weather", "bad", "empty"]
    assert out.tool_calls[0].arguments == {"origin": "metro", "dest": "opera"}
    assert out.tool_calls[1].arguments == {"at": "13:30"}
    assert out.tool_calls[2].arguments == {"at": "14:00"}
    assert out.tool_calls[3].arguments_error and out.tool_calls[4].arguments == {}
    sent = sdk.calls[0]
    assert sent["tools"][0]["type"] == "function" and sent["tools"][0]["function"]["name"] == "compare_routes"
    assert sent["timeout"] == 30 and sent["model"] == "claude-sonnet-5-5"
    assert out.usage["prompt_tokens"] == 10


def test_assistant_message_round_trip():
    res = ChatResult(content="hi", tool_calls=[parse_call()])
    m = assistant_message(res)
    assert m["tool_calls"][0]["function"]["arguments"] == '{"a": 1}' and m["tool_calls"][0]["id"] == "x"


def parse_call():
    from zill.agent.llm import ToolCall

    return ToolCall(id="x", name="t", arguments={"a": 1})


def test_parse_tool_args_variants():
    assert parse_tool_args(None) == ({}, None)
    assert parse_tool_args('"{\\"a\\": 2}"') == ({"a": 2}, None)  # double encoded
    assert parse_tool_args("[1,2]")[1] is not None
    assert parse_tool_args('blah {"q": 1} blah') == ({"q": 1}, None)


def test_retries_twice_then_succeeds():
    sdk = FakeSDK(responses=[resp("ok")], fail_times=2)
    assert client(sdk).chat([{"role": "user", "content": "x"}]).content == "ok"
    assert len(sdk.calls) == 3


def test_gives_up_after_retries():
    sdk = FakeSDK(fail_times=99)
    with pytest.raises(LLMError):
        client(sdk).chat([{"role": "user", "content": "x"}], model="m")
    assert len(sdk.calls) == 3  # initial + 2 retries


def test_404_falls_through_model_list():
    class NotFoundError(Exception):
        pass

    sdk = FakeSDK(responses=[resp("from haiku", model="claude-haiku-5-5")])
    seen: list[str] = []
    orig = sdk._create

    def create(**kw):
        seen.append(kw["model"])
        if kw["model"] != "claude-haiku-5-5":
            raise NotFoundError("no such model")
        return orig(**kw)

    sdk.chat = NS(completions=NS(create=create))
    out = client(sdk).chat([{"role": "user", "content": "x"}])
    assert out.content == "from haiku"
    assert seen[0] == "claude-sonnet-5-5" and seen[-1] == "claude-haiku-5-5"


def test_auth_error_not_retried():
    class AuthenticationError(Exception):
        pass

    sdk = FakeSDK(fail_times=5, fail_exc=AuthenticationError("bad key sk-SECRET"))
    with pytest.raises(LLMError) as ei:
        client(sdk).chat([{"role": "user", "content": "x"}])
    assert len(sdk.calls) == 1
    assert "SECRET" not in str(ei.value)  # key material never surfaces


def test_content_parts_supported():
    sdk = FakeSDK(responses=[resp([{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}])])
    assert client(sdk).chat([{"role": "user", "content": "x"}]).content == "hello"


def test_fake_llm_script():
    f = FakeLLM(["a", ChatResult(content="b"), lambda m, t: ChatResult(content=f"n={len(m)}")])
    msgs = [{"role": "user", "content": "x"}]
    assert [f.chat(msgs).content for _ in range(3)] == ["a", "b", "n=1"]
    with pytest.raises(LLMError):
        f.chat(msgs)
