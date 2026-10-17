import asyncio

import pytest
from claude_agent_sdk import ResultMessage

from app import config, llm

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def result_msg(**kw) -> ResultMessage:
    base = dict(subtype="success", duration_ms=12, duration_api_ms=10, is_error=False, num_turns=1, session_id="s",
                total_cost_usd=0.01, usage={"input_tokens": 100, "cache_read_input_tokens": 20,
                                            "cache_creation_input_tokens": 5, "output_tokens": 7},
                structured_output={"ok": True})
    return ResultMessage(**{**base, **kw})


def fake_query(messages=None, delay=0.0):
    captured = {}

    async def query(prompt, options):
        captured["prompt"], captured["options"] = prompt, options
        await asyncio.sleep(delay)
        for m in messages or []:
            yield m

    return query, captured


def test_configure_default_and_switch():
    assert llm.current_provider() == "claude"
    llm.configure("codex")
    assert llm.current_provider() == "codex"
    llm.configure("claude")
    assert llm.current_provider() == "claude"


def test_configure_rejects_unknown():
    with pytest.raises(ValueError, match="unknown provider: gpt"):
        llm.configure("gpt")
    assert llm.current_provider() == "claude"


def test_login_command_and_message_per_provider():
    assert llm.LOGIN_COMMAND == {"claude": "claude login", "codex": "codex login"}
    assert "`claude login`" in llm.auth_message("claude")
    assert "`codex login`" in llm.auth_message("codex")


def test_claude_path_uses_model_and_sums_tokens(monkeypatch):
    query, captured = fake_query([result_msg()])
    monkeypatch.setattr(llm, "query", query)
    monkeypatch.setattr(config, "CLAUDE_MODEL", "claude-test-model")
    res = asyncio.run(llm.ask_json("hello", SCHEMA, system_prompt="sys"))
    assert res.data == {"ok": True}
    assert (res.cost_usd, res.duration_ms, res.input_tokens, res.output_tokens) == (0.01, 12, 125, 7)
    assert captured["prompt"] == "hello"
    assert captured["options"].model == "claude-test-model"
    assert captured["options"].system_prompt == "sys"
    assert captured["options"].output_format == {"type": "json_schema", "schema": SCHEMA}


def test_claude_path_auth_error(monkeypatch):
    query, _ = fake_query([result_msg(is_error=True, api_error_status=401, result="Not logged in", structured_output=None)])
    monkeypatch.setattr(llm, "query", query)
    with pytest.raises(llm.LLMAuthError, match="claude login"):
        asyncio.run(llm.ask_json("p", SCHEMA))


def test_claude_path_timeout(monkeypatch):
    query, _ = fake_query([result_msg()], delay=5)
    monkeypatch.setattr(llm, "query", query)
    monkeypatch.setattr(config, "LLM_TIMEOUT_S", 0.05)
    with pytest.raises(llm.LLMError, match="timed out"):
        asyncio.run(llm.ask_json("p", SCHEMA))
