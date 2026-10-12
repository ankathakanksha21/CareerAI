import anthropic
import httpx
import pytest

import llm


@pytest.fixture(autouse=True)
def bedrock_env(no_env_file, monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "primary.model")
    monkeypatch.setenv("BEDROCK_API_KEY", "test-key")
    monkeypatch.delenv("BEDROCK_FALLBACK_MODEL_ID", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)


def http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://bedrock-mantle.us-east-1.api.aws/v1/chat/completions")
    return httpx.HTTPStatusError(f"{status}", request=request, response=httpx.Response(status, request=request))


@pytest.fixture
def calls(monkeypatch):
    """Replace the network call. Each entry of `script` is a reply, or an exception to raise."""
    seen = []

    def install(*script):
        replies = list(script)

        def fake_call(model, system, user, max_tokens):
            seen.append(model)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(llm, "_call", fake_call)
        return seen
    return install


def test_strip_reasoning_removes_think_block():
    assert llm.strip_reasoning('<think>{not json}</think>{"a":1}') == '{"a":1}'


def test_strip_reasoning_unterminated_block():
    assert llm.strip_reasoning("<think>abc") == ""


def test_strip_reasoning_closing_tag_only():
    # some servers drop the opening tag and send only the reasoning followed by </think>
    assert llm.strip_reasoning('thinking {x}</think>\n{"a":1}') == '{"a":1}'


def test_strip_reasoning_leaves_plain_text_alone():
    assert llm.strip_reasoning('  {"a":1}  ') == '{"a":1}'


def test_complete_json_ignores_braces_in_think(calls):
    calls('<think>{x}</think>\n```json\n{"a": 1}\n```')
    assert llm.complete_json("sys", "user") == {"a": 1}


def test_complete_json_accepts_a_top_level_array(calls):
    calls('[{"a": 1}]')
    assert llm.complete_json("sys", "user") == [{"a": 1}]


def test_complete_json_no_json_raises_value_error(calls):
    calls("I cannot help with that.")
    with pytest.raises(ValueError):
        llm.complete_json("sys", "user")


@pytest.mark.parametrize("reply", ['{"a": [1, 2]}}', '{"a": [1, 2]}`', '{"a": [1, 2]}"', '{"a": [1, 2]})',
                                   '{"a": [1, 2]}\nI hope this helps {really}'])
def test_complete_json_ignores_whatever_follows_the_json(calls, reply):
    """The model sometimes adds a stray bracket or quote after a complete answer."""
    calls(reply)
    assert llm.complete_json("sys", "user") == {"a": [1, 2]}


def test_complete_json_truncated_json_raises_value_error(calls):
    calls('{"items": [{"title": "cut off he')
    with pytest.raises(ValueError):
        llm.complete_json("sys", "user")


@pytest.mark.parametrize("status", [403, 404])
def test_fallback_used_on_403_and_404(calls, monkeypatch, status):
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "fallback.model")
    seen = calls(http_error(status), "from fallback")
    assert llm.complete("sys", "user") == "from fallback"
    assert seen == ["primary.model", "fallback.model"]


def test_fallback_used_on_anthropic_status_error(calls, monkeypatch):
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "fallback.model")
    request = httpx.Request("POST", "https://bedrock-mantle.us-east-1.api.aws/anthropic/v1/messages")
    refused = anthropic.NotFoundError("model not found", response=httpx.Response(404, request=request), body=None)
    seen = calls(refused, "from fallback")
    assert llm.complete("sys", "user") == "from fallback"
    assert seen == ["primary.model", "fallback.model"]


def test_no_fallback_on_500(calls, monkeypatch):
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "fallback.model")
    seen = calls(http_error(500))
    with pytest.raises(httpx.HTTPStatusError):
        llm.complete("sys", "user")
    assert seen == ["primary.model"]


def test_no_fallback_when_unset(calls):
    seen = calls(http_error(403))
    with pytest.raises(httpx.HTTPStatusError):
        llm.complete("sys", "user")
    assert seen == ["primary.model"]


def test_no_fallback_to_the_same_model(calls, monkeypatch):
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "primary.model")
    seen = calls(http_error(404))
    with pytest.raises(httpx.HTTPStatusError):
        llm.complete("sys", "user")
    assert seen == ["primary.model"]


def test_not_configured_without_model(calls, monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID")
    seen = calls("unused")
    with pytest.raises(llm.LLMNotConfigured):
        llm.complete("sys", "user")
    assert seen == []
