import asyncio
import json
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk import ResultError

from . import auth, config

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
class CodexProc(Protocol):
    def lines(self) -> AsyncIterator[str]: ...
    async def wait(self) -> int: ...
    def kill(self) -> None: ...
    async def stderr(self) -> str: ...


CodexRunner = Callable[[list[str], str], Awaitable[CodexProc]]


class _SubprocessCodex:
    def __init__(self, proc: asyncio.subprocess.Process, stdin: str):
        self._proc = proc
        self._stderr = asyncio.ensure_future(proc.stderr.read())
        self._feed = asyncio.ensure_future(self._write_stdin(stdin.encode()))

    async def _write_stdin(self, data: bytes) -> None:
        try:
            self._proc.stdin.write(data)
            await self._proc.stdin.drain()
            self._proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass

    async def lines(self) -> AsyncIterator[str]:
        while line := await self._proc.stdout.readline():
            yield line.decode(errors="replace").rstrip("\n")

    async def wait(self) -> int:
        return await self._proc.wait()

    def kill(self) -> None:
        try:
            self._proc.kill()
        except ProcessLookupError:
            pass

    async def stderr(self) -> str:
        return (await self._stderr).decode(errors="replace")


async def _spawn_codex(args: list[str], stdin: str) -> CodexProc:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    return _SubprocessCodex(proc, stdin)


codex_runner: CodexRunner = _spawn_codex


def to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI strict 변환: title/default 제거, 모든 object에 additionalProperties=false + required 전체"""
    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in ("title", "default"):
                continue
            if k in ("properties", "$defs", "definitions") and isinstance(v, dict):
                out[k] = {name: walk(sub) for name, sub in v.items()}
            else:
                out[k] = walk(v)
        if out.get("type") == "object" or "properties" in out:
            props = out.setdefault("properties", {})
            out["additionalProperties"] = False
            out["required"] = list(props)
        return out
    return walk(schema)


def codex_args(cwd: Path, schema_path: Path, out_path: Path) -> list[str]:
    args = [config.CODEX_BIN, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
            "-s", "read-only", "-C", str(cwd), "--output-schema", str(schema_path), "-o", str(out_path)]
    if config.CODEX_MODEL:
        args += ["-m", config.CODEX_MODEL]
    return args + ["-"]


async def _ask_codex(prompt: str, schema: dict[str, Any], system_prompt: str | None) -> LLMResult:
    # 미로그인 `codex exec`는 스스로 끝나지 않으므로 반드시 먼저 확인
    if not await auth.is_logged_in("codex"):
        raise LLMAuthError(auth_message("codex"))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-") as tmp:
        tmp_path = Path(tmp)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        schema_path, out_path = tmp_path / "schema.json", tmp_path / "out.json"
        schema_path.write_text(json.dumps(to_strict_schema(schema), ensure_ascii=False))
        stdin = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        proc = await codex_runner(codex_args(cwd, schema_path, out_path), stdin)

        usage: dict[str, Any] = {}
        auth_failed = False
        failed: str | None = None

        async def consume() -> None:
            nonlocal usage, auth_failed, failed
            async for line in proc.lines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "error" and "401 Unauthorized" in str(ev.get("message", "")):
                    auth_failed = True
                    return
                if kind == "turn.failed":
                    failed = str((ev.get("error") or {}).get("message") or ev)
                    return
                if kind == "turn.completed":
                    usage = ev.get("usage") or {}

        try:
            await asyncio.wait_for(consume(), timeout=config.LLM_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise LLMError(f"codex timed out after {config.LLM_TIMEOUT_S:g}s") from None
        except asyncio.CancelledError:
            proc.kill()
            raise

        if auth_failed:
            proc.kill()
            await proc.wait()
            raise LLMAuthError(auth_message("codex"))
        if failed:
            proc.kill()
            await proc.wait()
            raise LLMError(f"codex turn failed: {failed[:500]}")

        rc = await proc.wait()
        if rc != 0:
            if not await auth.is_logged_in("codex"):
                raise LLMAuthError(auth_message("codex"))
            raise LLMError(f"codex exited {rc}: {(await proc.stderr())[:500]}")
        if not out_path.exists():
            raise LLMError("codex produced no output file")
        try:
            data = json.loads(out_path.read_text())
        except json.JSONDecodeError as e:
            raise LLMError(f"codex output is not JSON: {e}") from None

    return LLMResult(
        data=data,
        cost_usd=0.0,
        duration_ms=int((time.monotonic() - started) * 1000),
        input_tokens=int(usage.get("input_tokens", 0)) + int(usage.get("cached_input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )
