import sys
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk import ResultError

MODEL = "claude-opus-5-5"


AUTH_MESSAGE = "Claude Code 로그인이 필요합니다. 터미널에서 `claude login`을 실행하세요."


class ClaudeAuthError(Exception):
    """Claude Code 세션이 없거나 만료됨. `claude login` 필요."""


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: Any
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int


def _is_auth(msg: str) -> bool:
    return "not logged in" in msg.lower() or "authentication" in msg.lower()


async def ask_json(prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> LLMResult:
    options = ClaudeAgentOptions(
        model=MODEL,
        tools=[],
        setting_sources=[],
        max_turns=2,
        system_prompt=system_prompt,
        output_format={"type": "json_schema", "schema": schema},
        stderr=lambda line: print(f"[claude stderr] {line}", file=sys.stderr),
    )
    result: ResultMessage | None = None
    auth_failed = False
    # 제너레이터 안에서 raise하면 SDK의 aclose()와 충돌하므로 플래그만 세우고 루프가 끝난 뒤 raise
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage) and msg.error == "authentication_failed":
                auth_failed = True
            if isinstance(msg, ResultMessage):
                result = msg
    except ResultError as e:
        if auth_failed or _is_auth(str(e)):
            raise ClaudeAuthError(AUTH_MESSAGE) from None
        raise LLMError(str(e)) from e

    if auth_failed or (result and result.is_error and (result.api_error_status == 401 or _is_auth(result.result or ""))):
        raise ClaudeAuthError(AUTH_MESSAGE)
    if result is None:
        raise LLMError("no result message")
    if result.is_error:
        raise LLMError(f"{result.subtype}: {result.result} {result.errors or ''}")
    if result.structured_output is None:
        raise LLMError(f"no structured output: {(result.result or '')[:200]}")

    usage = result.usage or {}
    return LLMResult(
        data=result.structured_output,
        cost_usd=result.total_cost_usd or 0.0,
        duration_ms=result.duration_ms,
        input_tokens=int(usage.get("input_tokens", 0)) + int(usage.get("cache_read_input_tokens", 0))
        + int(usage.get("cache_creation_input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )
