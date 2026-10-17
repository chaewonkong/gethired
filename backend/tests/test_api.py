import asyncio
import time
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, llm, resume
from app.api import create_app
from app.jobs import JobManager
from app.llm import LLMAuthError
from app.matcher import Match
from app.profile import Preferences, Profile
from app.repository import Repository
from app.scrapers import RawPosting, Scraper

PROFILE = Profile(name="t", seniority="mid", years_experience=5, core_skills=["Go"], familiar_skills=[],
                  weak_or_learning=[], domains=["matchmaking"], notable_achievements=[],
                  preferences=Preferences(locations=[], visa_or_work_authorization=None, target_domains=[], target_roles=[]),
                  dealbreakers=[], summary="s")


def posting(company: str, eid: str, title: str) -> RawPosting:
    return RawPosting(company=company, external_id=eid, title=title, apply_url="https://x/" + eid, description="d" * 200)


class FakeScraper(Scraper):
    display_name: ClassVar[str] = "fake"
    careers_url: ClassVar[str] = "https://x"
    expected_count: ClassVar[int] = 1
    data: ClassVar[dict[str, list[RawPosting]]] = {}
    fail: ClassVar[set[str]] = set()

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        if self.company in self.fail:
            raise RuntimeError("boom")
        return self.data[self.company]


class A(FakeScraper, register=False):
    company = "a"


class B(FakeScraper, register=False):
    company = "b"


judge_calls: list[list[str]] = []


async def fake_judge(profile, postings):
    await asyncio.sleep(0.2)  # 진행 중 상태를 관찰할 수 있게
    judge_calls.append([p.external_id for p in postings])
    out = []
    for p in postings:
        level = "exclude" if "ios" in p.title.lower() else "strong"
        out.append(Match(external_id=p.external_id, fit_level=level, score=10 if level == "exclude" else 90,
                         gaps=[], summary="summary text", tech_stack=["Go"], fit_reason="reason " * 5))
    return out, []


async def auth_failing_judge(profile, postings):
    raise LLMAuthError("Not logged in")


async def load_profile(repo):
    return PROFILE


auth_calls: list[str] = []


def make_client(judge=fake_judge, logged_in=True, resume_dir=None, interests=("a", "b")):
    repo = Repository()
    repo.set_interests(list(interests), "T0")
    jobs = JobManager(repo, scrapers={"a": A, "b": B}, profile_loader=load_profile, judge_fn=judge)

    async def is_logged_in(provider: str):
        auth_calls.append(provider)
        return logged_in if isinstance(logged_in, bool) else logged_in[provider]

    app = create_app(repo, jobs, logged_in=is_logged_in, resume_dir=resume_dir or Path("/nonexistent"))
    return TestClient(app), repo


def wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        body = client.get(f"/api/scrape/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@pytest.fixture(autouse=True)
def reset():
    FakeScraper.data = {"a": [posting("a", "1", "Backend Go"), posting("a", "2", "iOS Engineer")],
                        "b": [posting("b", "3", "Server Dev")]}
    FakeScraper.fail = set()
    judge_calls.clear()
    auth_calls.clear()


def test_scrape_stores_graded_and_skips_excluded_then_incremental():
    client, repo = make_client()
    with client:
        r = client.post("/api/scrape")
        assert r.status_code == 202
        job = wait_job(client, r.json()["job_id"])
        assert job["status"] == "done"
        assert job["companies"]["a"] == {"status": "done", "fetched": 2, "new": 2, "stored": 1, "excluded": 1, "deleted": 0, "error": None}
        postings = client.get("/api/postings").json()
        assert [p["external_id"] for p in postings] == ["1", "3"]
        assert postings[0]["fit_level"] == "strong" and postings[0]["tech_stack"] == ["Go"]

        # 2회차: 같은 공고 → 재판정 없음 (excluded 포함)
        FakeScraper.data["a"].append(posting("a", "9", "New Backend"))
        job2 = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert job2["companies"]["a"]["new"] == 1
        assert sum(len(c) for c in judge_calls) == 4  # 3 + 1

        companies = {c["company"]: c for c in client.get("/api/companies").json()}
        assert companies["a"]["last_run"]["status"] == "done" and companies["a"]["last_run"]["fetched_count"] == 3


def test_soft_delete_when_posting_disappears_and_failed_company_isolated():
    client, repo = make_client()
    with client:
        wait_job(client, client.post("/api/scrape").json()["job_id"])
        FakeScraper.data["b"] = []  # 0건은 실패로 간주 → soft delete 안 함
        FakeScraper.fail = {"a"}
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert job["status"] == "done"
        assert job["companies"]["a"]["status"] == "failed" and "boom" in job["companies"]["a"]["error"]
        assert job["companies"]["b"]["status"] == "failed"
        assert [p["external_id"] for p in client.get("/api/postings").json()] == ["1", "3"]

        FakeScraper.fail = set()
        FakeScraper.data["a"] = [posting("a", "2", "iOS Engineer")]  # "1" 사라짐
        FakeScraper.data["b"] = [posting("b", "3", "Server Dev")]
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert job["companies"]["a"]["deleted"] == 1
        assert [p["external_id"] for p in client.get("/api/postings").json()] == ["3"]


def test_scrape_requires_login_and_running_job_is_reused():
    client, _ = make_client(logged_in=False)
    with client:
        r = client.post("/api/scrape")
        assert r.status_code == 401
        assert r.json() == {"code": "login_required", "provider": "claude", "message": llm.auth_message("claude")}
        assert "`claude login`" in r.json()["message"]
        assert client.get("/api/auth/status").json() == {"provider": "claude", "logged_in": False,
                                                         "login_command": "claude login"}

    client, _ = make_client()
    with client:
        first = client.post("/api/scrape").json()["job_id"]
        second = client.post("/api/scrape").json()["job_id"]
        assert first == second
        wait_job(client, first)
        assert client.get("/api/scrape/nope").status_code == 404
        assert client.post("/api/scrape", params={"companies": ["zzz"]}).status_code == 400


def test_provider_setting_reads_db_only_and_env_default(monkeypatch):
    client, repo = make_client()
    with client:
        assert client.get("/api/settings/provider").json() == {"provider": "claude", "chosen": False}
        assert auth_calls == []

        monkeypatch.setattr(config, "LLM_PROVIDER", "codex")
        assert client.get("/api/settings/provider").json() == {"provider": "codex", "chosen": False}
        assert client.get("/api/auth/status").json() == {"provider": "codex", "logged_in": True,
                                                         "login_command": "codex login"}
        assert auth_calls == ["codex"]

        monkeypatch.setattr(config, "LLM_PROVIDER", "gpt")
        assert client.get("/api/settings/provider").json() == {"provider": "claude", "chosen": False}

        repo.set_setting("provider", "codex", "T1")
        monkeypatch.setattr(config, "LLM_PROVIDER", "claude")
        assert client.get("/api/settings/provider").json() == {"provider": "codex", "chosen": True}


def test_put_provider_contract():
    client, repo = make_client(logged_in={"claude": True, "codex": False})
    with client:
        r = client.put("/api/settings/provider", json={"provider": "gpt"})
        assert r.status_code == 400 and r.json() == {"detail": "unknown provider: gpt"}
        assert client.get("/api/settings/provider").json()["chosen"] is False

        r = client.put("/api/settings/provider", json={"provider": "codex"})
        assert r.status_code == 200
        assert r.json() == {"provider": "codex", "logged_in": False, "login_command": "codex login"}
        assert r.json() == client.get("/api/auth/status").json()
        assert client.get("/api/settings/provider").json() == {"provider": "codex", "chosen": True}
        assert repo.get_setting("provider") == "codex"

        r = client.post("/api/scrape")
        assert r.status_code == 401
        assert r.json() == {"code": "login_required", "provider": "codex", "message": llm.auth_message("codex")}

        r = client.put("/api/settings/provider", json={"provider": "claude"})
        assert r.json() == {"provider": "claude", "logged_in": True, "login_command": "claude login"}


def test_put_provider_blocked_while_job_running():
    client, repo = make_client()
    with client:
        job_id = client.post("/api/scrape").json()["job_id"]
        r = client.put("/api/settings/provider", json={"provider": "codex"})
        assert r.status_code == 409
        assert r.json()["code"] == "job_running" and r.json()["message"]
        assert repo.get_setting("provider") is None

        wait_job(client, job_id)
        assert client.put("/api/settings/provider", json={"provider": "codex"}).status_code == 200


def test_job_configures_llm_with_resolved_provider(monkeypatch):
    configured: list[str] = []
    monkeypatch.setattr(llm, "configure", configured.append)
    client, repo = make_client()
    with client:
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert configured == ["claude"] and job["provider"] == "claude"

        repo.set_setting("provider", "codex", "T1")
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert configured == ["claude", "codex"] and job["provider"] == "codex"


def test_auth_error_during_judging_marks_job_auth_required():
    client, repo = make_client(judge=auth_failing_judge)
    with client:
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert job["status"] == "auth_required"
        assert {c["status"] for c in job["companies"].values()} == {"auth_required"}
        assert client.get("/api/postings").json() == []
        assert repo.judged_ids("a") == set()  # 재로그인 후 재판정 대상


def test_bookmark_put_delete():
    client, repo = make_client()
    with client:
        wait_job(client, client.post("/api/scrape").json()["job_id"])
        first = client.get("/api/postings").json()[0]
        assert first["bookmarked"] is False

        r = client.put(f"/api/postings/{first['id']}/bookmark")
        assert r.status_code == 200 and r.json() == {"posting_id": first["id"], "bookmarked": True}
        assert [p["id"] for p in client.get("/api/postings").json() if p["bookmarked"]] == [first["id"]]
        assert repo.get_bookmark(first["id"])["deleted_at"] is None

        assert client.delete(f"/api/postings/{first['id']}/bookmark").json()["bookmarked"] is False
        assert not any(p["bookmarked"] for p in client.get("/api/postings").json())
        assert repo.get_bookmark(first["id"])["deleted_at"] is not None

        assert client.put("/api/postings/9999/bookmark").status_code == 404


def test_hide_put_delete():
    client, repo = make_client()
    with client:
        wait_job(client, client.post("/api/scrape").json()["job_id"])
        first = client.get("/api/postings").json()[0]
        assert first["hidden"] is False

        r = client.put(f"/api/postings/{first['id']}/hide")
        assert r.status_code == 200 and r.json() == {"posting_id": first["id"], "hidden": True}
        assert [p["id"] for p in client.get("/api/postings").json() if p["hidden"]] == [first["id"]]
        assert repo.get_hidden(first["id"])["deleted_at"] is None

        assert client.delete(f"/api/postings/{first['id']}/hide").json()["hidden"] is False
        assert not any(p["hidden"] for p in client.get("/api/postings").json())
        assert repo.get_hidden(first["id"])["deleted_at"] is not None

        assert client.put("/api/postings/9999/hide").status_code == 404
        assert client.delete("/api/postings/9999/hide").status_code == 404


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_resume_upload_overwrite_and_coexist(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    with client:
        assert client.get("/api/resume").json() == []
        res = client.put("/api/resume/resume.md", content=b"v1")
        assert res.status_code == 200 and res.json() == {}
        assert (d / "resume.md").read_text() == "v1"
        client.put("/api/resume/resume.md", content=b"v2")
        client.put("/api/resume/portfolio.md", content=b"p", headers={"content-type": "application/json"})
        assert (d / "resume.md").read_text() == "v2"
        files = client.get("/api/resume").json()
        assert [f["name"] for f in files] == ["portfolio.md", "resume.md"]
        assert files[1]["size"] == 2 and files[1]["updated_at"]


def test_resume_pdf_upload_list_delete(tmp_path):
    d = tmp_path / "resume"
    pdf = (FIXTURES / "resume_sample.pdf").read_bytes()
    client, _ = make_client(resume_dir=d)
    with client:
        res = client.put("/api/resume/cv.pdf", content=pdf, headers={"content-type": "application/octet-stream"})
        assert res.status_code == 200 and res.json() == {}
        assert (d / "cv.pdf").read_bytes() == pdf
        client.put("/api/resume/notes.md", content=b"n")
        files = client.get("/api/resume").json()
        assert [(f["name"], f["size"]) for f in files] == [("cv.pdf", len(pdf)), ("notes.md", 1)]
        assert sorted(f.name for f in d.iterdir()) == ["cv.pdf", "notes.md"]
        assert client.delete("/api/resume/cv.pdf").status_code == 200
        assert [f["name"] for f in client.get("/api/resume").json()] == ["notes.md"]
        assert client.delete("/api/resume/cv.pdf").status_code == 404


def test_resume_blank_pdf_rejected_and_not_saved(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    with client:
        res = client.put("/api/resume/scan.pdf", content=(FIXTURES / "resume_blank.pdf").read_bytes())
        assert res.status_code == 400
        assert res.json()["detail"] == "텍스트를 추출할 수 없는 PDF입니다 (스캔·이미지 PDF): scan.pdf"
        assert client.put("/api/resume/broken.pdf", content=b"%PDF-1.4 not a pdf").status_code == 400
        assert client.get("/api/resume").json() == []
        assert list(d.iterdir()) == []


def test_resume_rejects_invalid_files(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    with client:
        res = client.put("/api/resume/resume.txt", content=b"x")
        assert res.status_code == 400
        assert res.json()["detail"] == "md 또는 pdf 파일만 업로드할 수 있습니다: resume.txt"
        assert client.put("/api/resume/resume.PDF", content=b"x").status_code == 400
        assert client.put("/api/resume/..%2Fescape.md", content=b"x").status_code in (400, 404)
        assert client.put("/api/resume/.hidden.md", content=b"x").status_code == 400
        for bad in ("../escape.md", "sub/x.md", ".tmp.pdf"):
            with pytest.raises(ValueError):
                resume._path(d, bad)
        assert not (tmp_path / "escape.md").exists()
        assert not d.exists() or list(d.iterdir()) == []


def test_resume_large_body_streams_to_disk(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    body = b"x" * (5 * 1024 * 1024)
    with client:
        assert client.put("/api/resume/big.md", content=body).status_code == 200
        assert (d / "big.md").stat().st_size == len(body)
        assert client.get("/api/resume").json()[0]["size"] == len(body)


def test_resume_temp_file_hidden_from_list(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    with client:
        client.put("/api/resume/a.md", content=b"a")
        (d / ".a.md.tmp").write_bytes(b"partial")
        (d / ".hidden.pdf").write_bytes(b"x")
        (d / "notes.txt").write_text("t")
        assert [f["name"] for f in client.get("/api/resume").json()] == ["a.md"]


def test_resume_save_failure_removes_temp(tmp_path):
    d = tmp_path / "resume"

    async def chunks():
        yield b"part"
        raise RuntimeError("client gone")

    with pytest.raises(RuntimeError):
        asyncio.run(resume.save(d, "x.md", chunks()))
    assert list(d.iterdir()) == []


def test_resume_delete(tmp_path):
    d = tmp_path / "resume"
    client, _ = make_client(resume_dir=d)
    with client:
        client.put("/api/resume/a.md", content=b"a")
        assert client.delete("/api/resume/a.md").status_code == 200
        assert client.get("/api/resume").json() == []
        assert client.delete("/api/resume/a.md").status_code == 404
        assert client.delete("/api/resume/a.txt").status_code == 400


def test_interests_put_and_toggle():
    client, repo = make_client(interests=())
    with client:
        assert [c["interested"] for c in client.get("/api/companies").json()] == [False, False]
        assert client.put("/api/interests", json={"companies": []}).status_code == 400
        assert client.put("/api/interests", json={"companies": ["zzz"]}).status_code == 400
        assert client.put("/api/interests", json={"companies": ["b"]}).json() == {"companies": ["b"]}
        assert {c["company"]: c["interested"] for c in client.get("/api/companies").json()} == {"a": False, "b": True}

        assert client.put("/api/companies/a/interest").json() == {"company": "a", "interested": True}
        assert client.delete("/api/companies/b/interest").json() == {"company": "b", "interested": False}
        assert repo.list_interests() == ["a"]
        assert client.put("/api/companies/zzz/interest").status_code == 400

        client.delete("/api/companies/a/interest")
        assert repo.list_interests() == []


def test_scrape_targets_only_interest_companies_and_keeps_postings_on_unstar():
    client, repo = make_client(interests=())
    with client:
        assert client.post("/api/scrape").status_code == 400

        client.put("/api/interests", json={"companies": ["b"]})
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert list(job["companies"]) == ["b"]
        assert judge_calls == [["3"]]

        client.put("/api/companies/a/interest")
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert sorted(job["companies"]) == ["a", "b"]

        client.delete("/api/companies/b/interest")
        assert "b" in {p["company"] for p in client.get("/api/postings").json()}
        job = wait_job(client, client.post("/api/scrape").json()["job_id"])
        assert list(job["companies"]) == ["a"]
