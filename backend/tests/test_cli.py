import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import ClassVar

import pytest
from filelock import FileLock

from app import cli, config, demo
from app.jobs import JobManager
from app.llm import LLMAuthError
from app.matcher import Match
from app.repository import Repository, set_fixed_now
from app.scrapers import REGISTRY, RawPosting, Scraper

BACKEND = Path(__file__).parent.parent
FIXTURES = BACKEND / "fixtures"

STATUS_KEYS = {"resume_count", "provider", "chosen", "interests", "last_success", "stale", "job_running"}
RUN_KEYS = {"id", "company", "started_at", "finished_at", "status", "error", "fetched_count"}
POSTING_KEYS = {"id", "company", "title", "fit_level", "score", "fit_reason", "apply_url", "deadline", "scraped_at"}
FULL_KEYS = POSTING_KEYS | {"summary", "gaps"}
COMPANY_KEYS = {"company", "display_name", "careers_url", "last_run", "interested"}
JOB_KEYS = {"job_id", "status", "provider", "started_at", "finished_at", "cost_usd", "error", "companies"}
STATE_KEYS = {"status", "fetched", "new", "stored", "excluded", "deleted", "error"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("GETHIRED_DEMO", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "RESUME_DIR", tmp_path / "resume")
    yield
    set_fixed_now(None)


def run(capfd, *argv: str) -> tuple[int, object]:
    code = cli.main(list(argv))
    out = capfd.readouterr().out
    return code, json.loads(out)


def test_resume_add_list_rm(capfd, tmp_path):
    src = tmp_path / "src" / "me.md"
    src.parent.mkdir()
    src.write_text("# 이력서")

    code, files = run(capfd, "resume", "add", str(src), str(FIXTURES / "resume_sample.pdf"), "--json")
    assert code == 0
    assert [f["name"] for f in files] == ["me.md", "resume_sample.pdf"]
    assert (tmp_path / "resume" / "me.md").read_text() == "# 이력서"

    code, files = run(capfd, "resume", "list", "--json")
    assert code == 0 and len(files) == 2

    code, files = run(capfd, "resume", "rm", "me.md", "--json")
    assert code == 0 and [f["name"] for f in files] == ["resume_sample.pdf"]

    code, err = run(capfd, "resume", "rm", "me.md", "--json")
    assert code == 1 and err["code"] == "invalid_argument"


def test_resume_add_blank_pdf_is_invalid(capfd, tmp_path):
    code, err = run(capfd, "resume", "add", str(FIXTURES / "resume_blank.pdf"), "--json")
    assert code == 1
    assert set(err) == {"code", "message"} and err["code"] == "invalid_resume"
    assert not (tmp_path / "resume" / "resume_blank.pdf").exists()


def test_resume_add_bad_extension_and_missing_file(capfd, tmp_path):
    txt = tmp_path / "me.txt"
    txt.write_text("x")
    code, err = run(capfd, "resume", "add", str(txt), "--json")
    assert code == 1 and err["code"] == "invalid_resume"
    code, err = run(capfd, "resume", "add", str(tmp_path / "nope.md"), "--json")
    assert code == 1 and err["code"] == "invalid_argument"


def test_provider(capfd):
    assert run(capfd, "provider", "--json") == (0, {"provider": "claude", "chosen": False})
    assert run(capfd, "provider", "codex", "--json") == (0, {"provider": "codex", "chosen": True})
    assert run(capfd, "provider", "--json") == (0, {"provider": "codex", "chosen": True})

    code, err = run(capfd, "provider", "gemini", "--json")
    assert code == 1 and err["code"] == "invalid_argument"


def test_companies_and_interest(capfd):
    code, rows = run(capfd, "companies", "--json")
    assert code == 0
    assert [r["company"] for r in rows] == list(REGISTRY)
    assert set(rows[0]) == {"company", "display_name", "careers_url", "last_run", "interested"}
    assert not any(r["interested"] for r in rows)

    assert run(capfd, "interest", "add", "toss", "daangn", "--json") == (0, {"companies": ["daangn", "toss"]})
    assert run(capfd, "interest", "rm", "toss", "--json") == (0, {"companies": ["daangn"]})
    _, rows = run(capfd, "companies", "--json")
    assert [r["company"] for r in rows if r["interested"]] == ["daangn"]

    code, err = run(capfd, "interest", "add", "nope", "--json")
    assert code == 1 and err["code"] == "invalid_argument" and "nope" in err["message"]


def test_human_output_and_errors_on_stderr(capfd, tmp_path):
    assert cli.main(["interest", "add", "toss"]) == 0
    assert cli.main(["companies"]) == 0
    out = capfd.readouterr().out
    assert "toss" in out and "company" in out.splitlines()[1]

    assert cli.main(["resume", "add", str(FIXTURES / "resume_blank.pdf")]) == 1
    cap = capfd.readouterr()
    assert cap.out == "" and cap.err.startswith("error: ")


def test_parse_error_is_json(capfd):
    code, err = run(capfd, "resume", "--json")
    assert code == 1 and err["code"] == "invalid_argument"


def test_demo_requires_paths(capfd, monkeypatch, tmp_path):
    monkeypatch.setenv("GETHIRED_DEMO", "1")
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "demo-resume"))
    code, err = run(capfd, "companies", "--json")
    assert code == 1 and err["code"] == "invalid_argument"
    assert not config.DB_PATH.exists()


def test_demo_uses_demo_scrapers_and_paths(capfd, monkeypatch, tmp_path):
    monkeypatch.setenv("GETHIRED_DEMO", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "demo" / "app.db"))
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "demo" / "resume"))

    assert run(capfd, "interest", "add", "toss", "--json") == (0, {"companies": ["toss"]})
    _, rows = run(capfd, "companies", "--json")
    assert [r["company"] for r in rows] == list(demo.COMPANIES)
    code, err = run(capfd, "interest", "add", "coupang", "--json")
    assert code == 1
    assert (tmp_path / "demo" / "app.db").exists() and not config.DB_PATH.exists()


def test_pops_api_keys(capfd, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    run(capfd, "paths", "--json")
    assert "ANTHROPIC_API_KEY" not in os.environ and "OPENAI_API_KEY" not in os.environ


def test_paths_json(capfd, tmp_path):
    assert run(capfd, "paths", "--json") == (0, {"home": str(tmp_path), "db": str(tmp_path / "app.db"),
                                                  "resume": str(tmp_path / "resume"),
                                                  "frontend": str(config.FRONTEND_DIST)})


# --- status / scrape / postings ---
class Fake(Scraper, register=False):
    display_name: ClassVar[str] = "fake"
    careers_url: ClassVar[str] = "https://x"
    expected_count: ClassVar[int] = 1

    async def fetch(self, client) -> list[RawPosting]:
        return [RawPosting(company=self.company, external_id="1", title=f"Backend {self.company}",
                           apply_url=f"https://x/{self.company}", description="d" * 200)]


class Broken(Fake, register=False):
    async def fetch(self, client) -> list[RawPosting]:
        raise RuntimeError("boom")


class FakeA(Fake, register=False):
    company = "a"


class FakeB(Fake, register=False):
    company = "b"


class BrokenA(Broken, register=False):
    company = "a"


class BrokenB(Broken, register=False):
    company = "b"


async def fake_judge(profile, postings):
    return [Match(external_id=p.external_id, fit_level="strong", score=90, gaps=["g"], summary="summary text",
                  tech_stack=[], fit_reason="reason " * 5) for p in postings], []


async def fake_profile(repo):
    return demo.PROFILE


@pytest.fixture
def fake(monkeypatch):
    """GETHIRED_DEMO 없이 Env.jobs·scrapers를 fake로"""
    opts = {"scrapers": {"a": FakeA, "b": FakeB}, "judge": fake_judge, "profile": fake_profile, "logged_in": True}

    def jobs(self, repo):
        async def logged_in(provider):
            return opts["logged_in"]
        return JobManager(repo, scrapers=opts["scrapers"], profile_loader=opts["profile"], judge_fn=opts["judge"],
                          lock_path=self.db_path.with_suffix(".lock"), logged_in=logged_in)

    monkeypatch.setattr(cli.Env, "jobs", jobs)
    monkeypatch.setattr(cli.Env, "scrapers", lambda self: opts["scrapers"])
    return opts


def onboard(capfd, *companies: str) -> None:
    assert run(capfd, "provider", "claude", "--json")[0] == 0
    if companies:
        assert run(capfd, "interest", "add", *companies, "--json")[0] == 0


def demo_env(monkeypatch, tmp_path) -> dict[str, str]:
    env = {"GETHIRED_DEMO": "1", "DB_PATH": str(tmp_path / "demo" / "app.db"),
           "RESUME_DIR": str(tmp_path / "demo" / "resume"), "DEMO_JUDGE_DELAY_S": "0"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


def test_demo_golden_path(capfd, monkeypatch, tmp_path):
    demo_env(monkeypatch, tmp_path)
    resume_md = tmp_path / "me.md"
    resume_md.write_text("# 홍길동")

    onboard(capfd)
    code, before = run(capfd, "status", "--json")
    assert code == 0
    assert (before["resume_count"], before["interests"], before["stale"], before["job_running"]) == (0, [], True, False)

    assert run(capfd, "resume", "add", str(resume_md), "--json")[0] == 0
    assert run(capfd, "interest", "add", "toss", "daangn", "--json")[0] == 0
    code, job = run(capfd, "scrape", "--json")
    assert code == 0 and job["status"] == "done" and job["failed"] == []
    assert job["finished_at"] == demo.FIXED_NOW

    code, strong = run(capfd, "postings", "--json", "--min-level", "strong")
    assert code == 0
    assert Counter(p["company"] for p in strong) == {"toss": 1, "daangn": 1}

    code, after = run(capfd, "status", "--json")
    assert code == 0
    assert (after["resume_count"], after["interests"], after["stale"], after["job_running"]) == \
        (1, ["daangn", "toss"], False, False)
    assert set(after["last_success"]) == {"toss", "daangn"}


def test_json_key_sets(capfd, fake, tmp_path):
    onboard(capfd, "a", "b")
    code, job = run(capfd, "scrape", "--json")
    assert code == 0
    assert set(job) == JOB_KEYS | {"failed"}
    assert all(set(s) == STATE_KEYS for s in job["companies"].values())

    code, status = run(capfd, "status", "--json")
    assert set(status) == STATUS_KEYS
    assert all(set(r) == RUN_KEYS for r in status["last_success"].values())

    _, rows = run(capfd, "postings", "--json")
    assert len(rows) == 2 and all(set(r) == POSTING_KEYS for r in rows)
    _, rows = run(capfd, "postings", "--json", "--full")
    assert all(set(r) == FULL_KEYS for r in rows) and rows[0]["gaps"] == ["g"]

    _, rows = run(capfd, "companies", "--json")
    assert all(set(r) == COMPANY_KEYS and set(r["last_run"]) == RUN_KEYS for r in rows)

    code, err = run(capfd, "postings", "--json", "--since", "abc")
    assert code == 1 and set(err) == {"code", "message"}


def test_scrape_partial_failure_exit_0(capfd, fake):
    fake["scrapers"] = {"a": FakeA, "b": BrokenB}
    onboard(capfd, "a", "b")
    code, job = run(capfd, "scrape", "--json")
    assert code == 0
    assert job["failed"] == [{"company": "b", "error": "RuntimeError: boom"}]
    assert set(job["failed"][0]) == {"company", "error"}


def test_scrape_all_failed(capfd, fake):
    fake["scrapers"] = {"a": BrokenA, "b": BrokenB}
    onboard(capfd, "a", "b")
    code, err = run(capfd, "scrape", "--json")
    assert code == 1 and err["code"] == "all_failed"
    assert set(err) == {"code", "message", "job"} and set(err["job"]) == JOB_KEYS


def test_scrape_profile_failed(capfd, fake):
    async def broken_profile(repo):
        raise RuntimeError("no resume")
    fake["profile"] = broken_profile
    onboard(capfd, "a", "b")
    code, err = run(capfd, "scrape", "--json")
    assert code == 1 and err["code"] == "profile_failed"
    assert err["job"]["error"].startswith("profile: ")


def test_scrape_no_targets(capfd, fake):
    onboard(capfd)
    code, err = run(capfd, "scrape", "--json")
    assert code == 1 and err["code"] == "no_targets"
    code, err = run(capfd, "scrape", "nope", "--json")
    assert code == 1 and err["code"] == "no_targets" and "nope" in err["message"]


def test_job_running(capfd, fake, tmp_path):
    onboard(capfd, "a", "b")
    other = FileLock(tmp_path / "app.lock")
    other.acquire()
    try:
        code, err = run(capfd, "scrape", "--json")
        assert code == 1 and err["code"] == "job_running"
        code, err = run(capfd, "provider", "codex", "--json")
        assert code == 1 and err["code"] == "job_running"
        assert run(capfd, "status", "--json")[1]["job_running"] is True
    finally:
        other.release()
    assert run(capfd, "provider", "--json")[1]["provider"] == "claude"


def test_not_onboarded(capfd, tmp_path):
    for argv in (["status"], ["postings"]):
        code, err = run(capfd, *argv, "--json")
        assert code == 1 and err == {"code": "not_onboarded", "message": err["message"]}
    assert not (tmp_path / "app.db").exists()


def test_postings_invalid_since(capfd, fake):
    onboard(capfd, "a")
    code, err = run(capfd, "postings", "--since", "abc", "--json")
    assert code == 1 and err["code"] == "invalid_argument"


def test_login_required_precheck(capfd, fake):
    fake["logged_in"] = False
    onboard(capfd, "a", "b")
    code, err = run(capfd, "scrape", "--json")
    assert code == 3
    assert err == {"code": "login_required", "message": err["message"], "login_command": "claude login"}


def test_login_required_midway(capfd, fake):
    async def expired(profile, postings):
        raise LLMAuthError("expired")
    fake["judge"] = expired
    onboard(capfd, "a", "b")
    code, err = run(capfd, "scrape", "--json")
    assert code == 3 and err["code"] == "login_required" and err["login_command"] == "claude login"
    assert set(err) == {"code", "message", "login_command", "job"} and err["job"]["status"] == "auth_required"


def test_postings_filters(capfd, fake, tmp_path):
    onboard(capfd, "a", "b")
    run(capfd, "scrape", "--json")
    _, rows = run(capfd, "postings", "--json", "--since", "24h")
    assert {r["company"] for r in rows} == {"a", "b"}
    _, rows = run(capfd, "postings", "--json", "--company", "a", "--company", "b", "--limit", "1")
    assert len(rows) == 1
    _, rows = run(capfd, "postings", "--json", "--company", "b")
    assert [r["company"] for r in rows] == ["b"]

    repo = Repository(tmp_path / "app.db")
    repo.set_hidden(rows[0]["id"], True, "T")
    repo.close()
    assert run(capfd, "interest", "rm", "a", "--json")[0] == 0
    assert run(capfd, "postings", "--json") == (0, [])


def test_status_subprocess_stdout_is_pure_json(capfd, tmp_path):
    onboard(capfd)
    env = {k: v for k, v in os.environ.items() if k != "GETHIRED_DEMO"}
    env |= {"GETHIRED_HOME": str(tmp_path), "DB_PATH": str(tmp_path / "app.db"), "RESUME_DIR": str(tmp_path / "resume")}
    r = subprocess.run([sys.executable, "-m", "app", "status", "--json"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("\n") == 1 and set(json.loads(r.stdout)) == STATUS_KEYS


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_read_commands_in_unwritable_home(capfd, fake, tmp_path):
    onboard(capfd, "a", "b")
    assert run(capfd, "scrape", "--json")[0] == 0
    assert (tmp_path / "app.lock").exists()
    before = sorted(os.listdir(tmp_path))
    tmp_path.chmod(0o555)
    try:
        for argv in (["status"], ["postings"], ["companies"]):
            assert run(capfd, *argv, "--json")[0] == 0, argv
    finally:
        tmp_path.chmod(0o755)
    assert sorted(os.listdir(tmp_path)) == before


def _read_until(fd: int, needle: bytes, timeout: float) -> bytes:
    buf, deadline = b"", time.monotonic() + timeout
    while needle not in buf:
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([fd], [], [], left)[0]:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        buf += chunk
    return buf


def test_ctrl_c_exit_130(capfd, monkeypatch, tmp_path):
    env = demo_env(monkeypatch, tmp_path)
    onboard(capfd, "toss", "daangn")
    env = {**{k: v for k, v in os.environ.items()}, **env, "DEMO_JUDGE_DELAY_S": "5", "GETHIRED_HOME": str(tmp_path)}
    proc = subprocess.Popen([sys.executable, "-m", "app", "scrape", "--json"], cwd=BACKEND, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        err = _read_until(proc.stderr.fileno(), b": running", 30)
        assert b": running" in err, err
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
    assert proc.returncode == 130
    body = json.loads(out)
    assert body["code"] == "interrupted" and body["job"]["status"] == "interrupted"
    assert set(body) == {"code", "message", "job"}

    lock = FileLock(tmp_path / "demo" / "app.lock")
    lock.acquire(timeout=0)
    lock.release()
    with sqlite3.connect(tmp_path / "demo" / "app.db") as conn:
        statuses = [r[0] for r in conn.execute("SELECT status FROM scrape_runs")]
    assert statuses and "running" not in statuses
