import asyncio
import json

from . import config

STATUS_TIMEOUT_S = 15

_inflight: dict[str, asyncio.Future] = {}


async def is_logged_in(provider: str) -> bool:
    """provider CLI의 로그인 상태. CLI가 없거나 실패·타임아웃이면 False. 같은 provider의 동시 호출은 결과를 공유한다."""
    fut = _inflight.get(provider)
    if fut is None or fut.done():
        fut = asyncio.ensure_future(_check(provider))
        _inflight[provider] = fut
        fut.add_done_callback(lambda _: _inflight.pop(provider, None))
    return await asyncio.shield(fut)


async def _check(provider: str) -> bool:
    return await (_codex_status() if provider == "codex" else _claude_status())


async def _claude_status() -> bool:
    """`claude auth status`의 loggedIn"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "auth", "status", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return False
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=STATUS_TIMEOUT_S)
        return bool(json.loads(out.decode() or "{}").get("loggedIn"))
    except asyncio.TimeoutError:
        _kill(proc)
        return False
    except json.JSONDecodeError:
        return False


async def _codex_status() -> bool:
    """`codex login status`의 exit code 0"""
    try:
        proc = await asyncio.create_subprocess_exec(
            config.CODEX_BIN, "login", "status",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return False
    try:
        return await asyncio.wait_for(proc.wait(), timeout=STATUS_TIMEOUT_S) == 0
    except asyncio.TimeoutError:
        _kill(proc)
        return False


def _kill(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.kill()
    except ProcessLookupError:
        pass
