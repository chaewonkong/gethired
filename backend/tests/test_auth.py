import asyncio
from pathlib import Path

import pytest

from app import auth, config


def fake_bin(dir_: Path, name: str, body: str) -> Path:
    p = dir_ / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)
    return p


@pytest.fixture
def codex(tmp_path, monkeypatch):
    def make(body: str) -> Path:
        p = fake_bin(tmp_path, "codex", '[ "$1 $2" = "login status" ] || exit 2\n' + body)
        monkeypatch.setattr(config, "CODEX_BIN", str(p))
        return p
    return make


def test_codex_logged_in_is_exit_code(codex):
    codex('echo "Logged in using ChatGPT"; exit 0')
    assert asyncio.run(auth.is_logged_in("codex")) is True
    codex('echo "Not logged in" >&2; exit 1')
    assert asyncio.run(auth.is_logged_in("codex")) is False


def test_codex_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CODEX_BIN", str(tmp_path / "nope"))
    assert asyncio.run(auth.is_logged_in("codex")) is False


def test_claude_parses_logged_in_json(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    fake_bin(tmp_path, "claude", '[ "$1 $2" = "auth status" ] || exit 2; echo \'{"loggedIn": true}\'')
    assert asyncio.run(auth.is_logged_in("claude")) is True
    fake_bin(tmp_path, "claude", 'echo \'{"loggedIn": false}\'')
    assert asyncio.run(auth.is_logged_in("claude")) is False
    fake_bin(tmp_path, "claude", 'echo garbage')
    assert asyncio.run(auth.is_logged_in("claude")) is False


def test_claude_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert asyncio.run(auth.is_logged_in("claude")) is False


def test_concurrent_checks_share_one_subprocess(codex, tmp_path):
    counter = tmp_path / "count"
    codex(f'echo x >> "{counter}"; sleep 0.3; exit 0')

    async def go():
        return await asyncio.gather(*(auth.is_logged_in("codex") for _ in range(4)))

    assert asyncio.run(go()) == [True] * 4
    assert counter.read_text().count("x") == 1
    assert asyncio.run(auth.is_logged_in("codex")) is True
    assert counter.read_text().count("x") == 2
