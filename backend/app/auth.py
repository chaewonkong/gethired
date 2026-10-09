import asyncio
import json


async def is_logged_in() -> bool:
    """`claude auth status`의 loggedIn. CLI가 없거나 파싱 실패면 False."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "auth", "status", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return bool(json.loads(out.decode() or "{}").get("loggedIn"))
    except (FileNotFoundError, asyncio.TimeoutError, json.JSONDecodeError):
        return False
