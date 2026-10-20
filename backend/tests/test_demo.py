import asyncio
import time
from collections import Counter
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import config, demo, matcher, profile, repository
from app.matcher import level_for
from app.repository import now_iso, set_fixed_now
from app.scrapers import REGISTRY


@pytest.fixture(autouse=True)
def reset_fixed_now():
    yield
    set_fixed_now(None)


def all_postings():
    return [p for cls in demo.SCRAPERS.values() for p in asyncio.run(cls().fetch(None))]


def test_demo_scrapers_not_registered():
    assert not any(cls in REGISTRY.values() for cls in demo.SCRAPERS.values())
    assert set(demo.SCRAPERS) == set(demo.COMPANIES) <= set(REGISTRY)
    for name, cls in demo.SCRAPERS.items():
        assert cls.company == name
        assert cls.display_name == REGISTRY[name].display_name


def test_demo_postings_and_judgments():
    postings = all_postings()
    assert len(postings) == 8
    assert len({p.external_id for p in postings}) == 8
    assert all(p.company in demo.COMPANIES for p in postings)

    matches, results = asyncio.run(demo.judge(demo.PROFILE, postings))
    assert results == []
    assert [m.external_id for m in matches] == [p.external_id for p in postings]
    assert Counter(m.fit_level for m in matches) == {"strong": 2, "good": 3, "stretch": 3}
    assert all(level_for(m.score) == m.fit_level for m in matches)

    today = date.fromisoformat(demo.FIXED_NOW[:10])
    soon = [p for p in postings if p.deadline and 0 <= (p.deadline - today).days <= 7]
    assert [p.title for p in soon] == ["매칭 플랫폼 백엔드 엔지니어"]


def test_demo_matches_have_breakdown_and_lists():
    assert all(m.breakdown.total == m.score for m in demo.MATCHES.values())
    for m in demo.MATCHES.values():
        assert 3 <= len(m.requirements) <= 6 and 1 <= len(m.preferred) <= 4
        assert all(len(x.text) <= 80 and x.fit in matcher.FIT_MARKS for x in m.requirements + m.preferred)
    assert all(2 <= len(p.description.split("\n\n")) <= 3 for p in all_postings())


def test_demo_feedback(monkeypatch):
    monkeypatch.setenv("DEMO_JUDGE_DELAY_S", "0")
    items, result = asyncio.run(demo.feedback(demo.PROFILE, {}))
    assert len(items) == 3 and result.cost_usd == 0 and result.data is None


def test_demo_profile_is_fictional():
    assert demo.PROFILE.name == "홍길동"


def test_set_fixed_now():
    set_fixed_now("2026-01-01T00:00:00+00:00")
    assert now_iso() == "2026-01-01T00:00:00+00:00"
    set_fixed_now(None)
    assert now_iso() != "2026-01-01T00:00:00+00:00"


def wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        body = client.get(f"/api/scrape/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_make_app_golden_path(tmp_path, monkeypatch):
    async def boom(files):
        raise AssertionError("profile.extract called in demo")
    monkeypatch.setattr(profile, "extract", boom)
    monkeypatch.setenv("DEMO_JUDGE_DELAY_S", "0")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "app.db"))
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "resume"))
    app = demo.make_app()
    assert repository.now_iso() == demo.FIXED_NOW

    with TestClient(app) as client:
        assert client.put("/api/resume/resume.md", content="# 홍길동 이력서".encode()).status_code == 200
        assert client.put("/api/settings/provider", json={"provider": "claude"}).json()["logged_in"] is True
        assert client.get("/api/auth/status").json()["logged_in"] is True

        companies = client.get("/api/companies").json()
        assert [c["company"] for c in companies] == list(demo.COMPANIES)
        assert client.put("/api/interests", json={"companies": list(demo.COMPANIES)}).status_code == 200

        r = client.post("/api/scrape")
        assert r.status_code == 202
        job = wait_job(client, r.json()["job_id"])
        assert job["status"] == "done"
        assert all(s["status"] == "done" and s["stored"] == 2 for s in job["companies"].values())
        assert job["finished_at"] == demo.FIXED_NOW

        postings = client.get("/api/postings").json()
        assert len(postings) == 8
        assert Counter(p["fit_level"] for p in postings) == {"strong": 2, "good": 3, "stretch": 3}
        assert all(p["scraped_at"] == demo.FIXED_NOW for p in postings)

        pid = postings[0]["id"]
        detail = client.get(f"/api/postings/{pid}").json()
        assert detail["description"] and detail["breakdown"] and detail["requirements"] and detail["feedback"] is None
        monkeypatch.setenv("DEMO_JUDGE_DELAY_S", "0.3")
        r = client.post(f"/api/postings/{pid}/feedback")
        assert r.status_code == 200 and len(r.json()["feedback"]["items"]) == 3
        start = time.monotonic()
        r = client.post(f"/api/postings/{pid}/feedback")
        assert r.status_code == 200 and r.json()["feedback"]["current"] is True
        assert time.monotonic() - start < 0.3  # 캐시 적중: 지연 없이 반환
        assert client.get(f"/api/postings/{pid}").json()["feedback"]["items"] == r.json()["feedback"]["items"]

        for c in client.get("/api/companies").json():
            assert c["last_run"]["status"] == "done"
            assert c["last_run"]["finished_at"] == demo.FIXED_NOW

    assert (tmp_path / "db" / "app.db").exists()
    assert (tmp_path / "resume" / "resume.md").exists()


def test_make_app_without_env_uses_temp_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("RESUME_DIR", raising=False)
    monkeypatch.setattr(demo.tempfile, "mkdtemp", lambda prefix="": str(tmp_path / "demo"))
    (tmp_path / "demo").mkdir()

    app = demo.make_app()
    assert app.state.db_path == tmp_path / "demo" / "app.db"
    assert app.state.resume_dir == tmp_path / "demo" / "resume"
    assert app.state.db_path != config.DB_PATH
    assert app.state.resume_dir != config.RESUME_DIR
    assert app.state.db_path.exists()


def test_demo_app_not_created_on_import():
    assert not hasattr(demo, "app")


def test_main_demo_flag(monkeypatch, tmp_path):
    from app import cli as entry

    calls = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "resume"))

    entry.main(["--demo", "--no-open", "--port", "8123"])
    app, kw = calls[0]
    assert kw == {"host": "127.0.0.1", "port": 8123}
    assert app.state.db_path == tmp_path / "app.db"

    sentinel = object()
    monkeypatch.setattr(entry, "_load_app", lambda: sentinel)
    entry.main(["serve", "--no-open"])
    assert calls[-1] == (sentinel, {"host": "127.0.0.1", "port": 8000})


def test_main_reset_db_and_paths(monkeypatch, tmp_path, capsys):
    from app import cli as entry

    db = tmp_path / "app.db"
    db.write_bytes(b"")
    monkeypatch.setattr(config, "DB_PATH", db)
    assert entry.main(["reset-db"]) == 0
    assert not db.exists()
    entry.main(["reset-db"])
    assert "no db" in capsys.readouterr().out

    entry.main(["paths"])
    assert str(db) in capsys.readouterr().out


def test_make_jobs_uses_demo_fixtures(tmp_path):
    jobs = demo.make_jobs(repository.Repository(tmp_path / "app.db"), tmp_path / "app.lock")
    assert set(jobs.scrapers) == set(demo.COMPANIES)
    assert jobs.judge_fn is demo.judge and jobs.profile_loader is demo.load_profile
    assert jobs.logged_in is demo.logged_in and jobs.lock_path == tmp_path / "app.lock"
    assert repository.now_iso() == demo.FIXED_NOW


def test_demo_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "resume"))
    assert demo.demo_paths() == (None, tmp_path / "resume")


def test_demo_app_lazy_with_env(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("GETHIRED_DEMO", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("RESUME_DIR", str(tmp_path / "resume"))
    mod = importlib.reload(demo)
    assert "app" not in vars(mod)
    assert mod.app.state.db_path == tmp_path / "app.db"
    del mod.app
