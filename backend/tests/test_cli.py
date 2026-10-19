import json
import os
from pathlib import Path

import pytest

from app import cli, config, demo
from app.repository import set_fixed_now
from app.scrapers import REGISTRY

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
