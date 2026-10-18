import asyncio
import time
from collections import Counter
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import config, demo, repository
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
