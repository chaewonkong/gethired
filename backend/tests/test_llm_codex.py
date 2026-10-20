import asyncio
import json
from pathlib import Path

import pytest

from app import auth, config, llm
from app.matcher import Batch
from app.profile import Profile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
          "required": ["ok", "echo"]}


def fixture_lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


class FakeProc:
    def __init__(self, lines, rc=0, stderr="", hang=False):
        self._lines, self.rc, self._stderr, self.hang = lines, rc, stderr, hang
        self.killed = False
        self._released = asyncio.Event()

    async def lines(self):
        for line in self._lines:
            yield line
        if self.hang:
            await self._released.wait()

    async def wait(self):
        return -9 if self.killed else self.rc

    def kill(self):
        self.killed = True
        self._released.set()

    async def stderr(self):
        return self._stderr


class FakeRunner:
    def __init__(self, proc: FakeProc, out: dict | None = None):
        self.proc, self.out, self.calls = proc, out, []

    async def __call__(self, args, stdin):
        opts = dict(zip(args, args[1:], strict=False))
        cwd, schema_path, out_path = Path(opts["-C"]), Path(opts["--output-schema"]), Path(opts["-o"])
        self.calls.append({"args": args, "stdin": stdin, "cwd_empty": cwd.is_dir() and not any(cwd.iterdir()),
                           "schema": json.loads(schema_path.read_text())})
        if self.out is not None:
            out_path.write_text(json.dumps(self.out))
        return self.proc


@pytest.fixture
def codex(monkeypatch):
    llm.configure("codex")
    checks = []

    async def logged_in(provider):
        checks.append(provider)
        return True

    monkeypatch.setattr(auth, "is_logged_in", logged_in)
    monkeypatch.setattr(config, "CODEX_BIN", "/opt/codex")
    monkeypatch.setattr(config, "CODEX_MODEL", None)

    def use(proc: FakeProc, out: dict | None = None) -> FakeRunner:
        runner = FakeRunner(proc, out)
        monkeypatch.setattr(llm, "codex_runner", runner)
        return runner

    use.checks = checks
    return use


def ask(prompt="ping", system_prompt=None):
    return asyncio.run(llm.ask_json(prompt, SCHEMA, system_prompt=system_prompt))


# --- strict schema ---
def assert_strict(node, path="$"):
    if isinstance(node, list):
        for i, n in enumerate(node):
            assert_strict(n, f"{path}[{i}]")
        return
    if not isinstance(node, dict):
        return
    assert "title" not in node and "default" not in node, path
    if node.get("type") == "object":
        assert node["additionalProperties"] is False, path
        assert node["required"] == list(node["properties"]), path
    for k, v in node.items():
        assert_strict(v, f"{path}.{k}")


def test_strict_batch_matches_verified_fixture():
    strict = llm.to_strict_schema(Batch.model_json_schema())
    assert strict == json.loads((FIXTURES / "codex_batch_strict.json").read_text())
    assert_strict(strict)
    match = strict["$defs"]["Match"]
    assert match["properties"]["summary"] == {"minLength": 10, "type": "string"}
    assert match["properties"]["score"] == {"maximum": 100, "minimum": 0, "type": "integer"}


def test_strict_profile_recurses_into_defs():
    strict = llm.to_strict_schema(Profile.model_json_schema())
    assert_strict(strict)
    assert set(strict["required"]) == set(Profile.model_fields)
    prefs = strict["$defs"]["Preferences"]
    assert prefs["additionalProperties"] is False
    assert prefs["required"] == ["locations", "visa_or_work_authorization", "target_domains", "target_roles"]
    assert prefs["properties"]["visa_or_work_authorization"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_strict_keeps_property_named_title_and_defaults_removed():
    schema = {"type": "object", "title": "T", "properties": {"title": {"type": "string", "default": "x"},
                                                             "n": {"type": "integer", "minimum": 1}}}
    assert llm.to_strict_schema(schema) == {
        "type": "object", "properties": {"title": {"type": "string"}, "n": {"type": "integer", "minimum": 1}},
        "additionalProperties": False, "required": ["title", "n"]}


# --- command ---
def test_command_args_and_stdin(codex):
    runner = codex(FakeProc(fixture_lines("codex_ok.jsonl")), out={"ok": True, "echo": "pong"})
    res = ask("user prompt", system_prompt="system rules")
    call = runner.calls[0]
    args = call["args"]
    assert args[:9] == ["/opt/codex", "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
                        "-s", "read-only", "-C"]
    assert args[-1] == "-" and "-m" not in args
    assert "--output-schema" in args and "-o" in args
    assert call["cwd_empty"] is True
    assert call["schema"] == llm.to_strict_schema(SCHEMA)
    assert call["stdin"] == "system rules\n\nuser prompt"
    assert res.data == {"ok": True, "echo": "pong"}


def test_command_model_flag_and_no_system_prompt(codex, monkeypatch):
    monkeypatch.setattr(config, "CODEX_MODEL", "gpt-test")
    runner = codex(FakeProc(fixture_lines("codex_ok.jsonl")), out={"ok": True, "echo": "pong"})
    ask("only user")
    args = runner.calls[0]["args"]
    assert args[args.index("-m") + 1] == "gpt-test" and args[-1] == "-"
    assert runner.calls[0]["stdin"] == "only user"


# --- streams ---
def test_ok_stream_returns_data_and_usage(codex):
    codex(FakeProc(fixture_lines("codex_ok.jsonl")), out={"ok": True, "echo": "pong"})
    res = ask()
    assert res.data == {"ok": True, "echo": "pong"}
    assert (res.cost_usd, res.input_tokens, res.output_tokens) == (0.0, 14009, 19)
    assert res.duration_ms >= 0
    assert codex.checks == ["codex"]


def test_unauth_stream_kills_and_raises_auth(codex):
    proc = FakeProc(fixture_lines("codex_unauth.jsonl"), hang=True)
    codex(proc)
    with pytest.raises(llm.LLMAuthError, match="codex login"):
        ask()
    assert proc.killed is True


def test_turn_failed_raises_llm_error(codex):
    proc = FakeProc(fixture_lines("codex_turn_failed.jsonl"), rc=1)
    codex(proc)
    with pytest.raises(llm.LLMError, match="invalid_json_schema"):
        ask()


def test_precheck_false_skips_exec(codex, monkeypatch):
    async def not_logged_in(provider):
        return False

    monkeypatch.setattr(auth, "is_logged_in", not_logged_in)
    runner = codex(FakeProc([]))
    with pytest.raises(llm.LLMAuthError, match="codex login"):
        ask()
    assert runner.calls == []


def test_nonzero_exit_rechecks_login(codex, monkeypatch):
    answers = iter([True, False])

    async def logged_in(provider):
        return next(answers)

    monkeypatch.setattr(auth, "is_logged_in", logged_in)
    codex(FakeProc(fixture_lines("codex_ok.jsonl")[:2], rc=1, stderr="boom"))
    with pytest.raises(llm.LLMAuthError):
        ask()

    answers = iter([True, True])
    codex(FakeProc(fixture_lines("codex_ok.jsonl")[:2], rc=1, stderr="disk full"))
    with pytest.raises(llm.LLMError, match="exited 1: disk full"):
        ask()


def test_timeout_kills(codex, monkeypatch):
    monkeypatch.setattr(config, "LLM_TIMEOUT_S", 0.05)
    proc = FakeProc([], hang=True)
    codex(proc)
    with pytest.raises(llm.LLMError, match="timed out"):
        ask()
    assert proc.killed is True


def test_missing_output_file(codex):
    codex(FakeProc(fixture_lines("codex_ok.jsonl")))
    with pytest.raises(llm.LLMError, match="no output file"):
        ask()


# --- 기본 runner (asyncio subprocess) ---
def test_subprocess_runner_with_fake_binary(tmp_path, monkeypatch):
    llm.configure("codex")

    async def logged_in(provider):
        return True

    monkeypatch.setattr(auth, "is_logged_in", logged_in)
    received = tmp_path / "stdin.txt"
    script = tmp_path / "codex"
    script.write_text(
        "#!/bin/sh\n"
        f'cat > "{received}"\n'
        'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
        f'cat "{FIXTURES / "codex_ok.jsonl"}"\n'
        'echo \'{"ok":true,"echo":"pong"}\' > "$out"\n'
        'echo "some stderr" >&2\n')
    script.chmod(0o755)
    monkeypatch.setattr(config, "CODEX_BIN", str(script))

    res = ask("ping", system_prompt="sys")
    assert res.data == {"ok": True, "echo": "pong"}
    assert (res.input_tokens, res.output_tokens) == (14009, 19)
    assert received.read_text() == "sys\n\nping"


def test_subprocess_runner_nonzero_exit_reports_stderr(tmp_path, monkeypatch):
    llm.configure("codex")

    async def logged_in(provider):
        return True

    monkeypatch.setattr(auth, "is_logged_in", logged_in)
    script = tmp_path / "codex"
    script.write_text("#!/bin/sh\ncat > /dev/null\necho 'bad flag' >&2\nexit 2\n")
    script.chmod(0o755)
    monkeypatch.setattr(config, "CODEX_BIN", str(script))
    with pytest.raises(llm.LLMError, match="exited 2: bad flag"):
        ask()


def test_strict_batch_breakdown_nested_def_is_strict():
    strict = llm.to_strict_schema(Batch.model_json_schema())
    bd = strict["$defs"]["Breakdown"]
    assert bd["additionalProperties"] is False
    assert bd["required"] == ["skills", "domain", "seniority", "preferred"]
    assert all(bd["properties"][k] == {"type": "integer"} for k in bd["required"])  # 범위는 스키마로 강제하지 않는다
    match = strict["$defs"]["Match"]
    assert match["properties"]["breakdown"] == {"$ref": "#/$defs/Breakdown"}
    assert set(match["required"]) >= {"breakdown", "requirements", "preferred"}


def test_strict_batch_requirement_def_is_strict():
    strict = llm.to_strict_schema(Batch.model_json_schema())
    req = strict["$defs"]["Requirement"]
    assert req["additionalProperties"] is False and req["required"] == ["text", "fit"]
    assert req["properties"]["fit"] == {"enum": ["met", "partial", "unmet"], "type": "string"}
    assert strict["$defs"]["Match"]["properties"]["requirements"] == {"items": {"$ref": "#/$defs/Requirement"}, "type": "array"}
