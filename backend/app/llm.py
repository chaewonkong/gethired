import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk import ResultError

from . import config

PROVIDERS = ("claude", "codex")
LOGIN_COMMAND = {"claude": "claude login", "codex": "codex login"}
PROVIDER_NAME = {"claude": "Claude Code", "codex": "Codex"}


def auth_message(provider: str) -> str:
    return f"{PROVIDER_NAME[provider]} 로그인이 필요합니다. 터미널에서 `{LOGIN_COMMAND[provider]}`를 실행하세요."


class LLMAuthError(Exception):
    """provider CLI 세션이 없거나 만료됨. LOGIN_COMMAND[provider] 필요."""


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: Any
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int


_provider = "claude"


def configure(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    global _provider
    _provider = provider


def current_provider() -> str:
    return _provider


async def ask_json(prompt: str, schema: dict[str, Any], system_prompt: str | None = None) -> LLMResult:
    if _provider == "codex":
        return await _ask_codex(prompt, schema, system_prompt)
    return await _ask_claude(prompt, schema, system_prompt)


# --- claude ---
def _is_auth(msg: str) -> bool:
    return "not logged in" in msg.lower() or "authentication" in msg.lower()


async def _ask_claude(prompt: str, schema: dict[str, Any], system_prompt: str | None) -> LLMResult:
    options = ClaudeAgentOptions(
        model=config.CLAUDE_MODEL,
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
    async def consume() -> None:
        nonlocal result, auth_failed
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage) and msg.error == "authentication_failed":
                auth_failed = True
            if isinstance(msg, ResultMessage):
                result = msg

    try:
        await asyncio.wait_for(consume(), timeout=config.LLM_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise LLMError(f"claude timed out after {config.LLM_TIMEOUT_S:g}s") from None
    except ResultError as e:
        if auth_failed or _is_auth(str(e)):
            raise LLMAuthError(auth_message("claude")) from None
        raise LLMError(str(e)) from e

    if auth_failed or (result and result.is_error and (result.api_error_status == 401 or _is_auth(result.result or ""))):
        raise LLMAuthError(auth_message("claude"))
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


# --- codex ---
async def _ask_codex(prompt: str, schema: dict[str, Any], system_prompt: str | None) -> LLMResult:
    raise NotImplementedError("codex provider")
