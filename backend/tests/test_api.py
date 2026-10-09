import asyncio
import time
from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.jobs import JobManager
from app.llm import ClaudeAuthError
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
    raise ClaudeAuthError("Not logged in")


async def load_profile(repo):
    return PROFILE


def make_client(judge=fake_judge, logged_in=True):
    repo = Repository()
    jobs = JobManager(repo, scrapers={"a": A, "b": B}, profile_loader=load_profile, judge_fn=judge)

    async def is_logged_in():
        return logged_in

    return TestClient(create_app(repo, jobs, logged_in=is_logged_in)), repo


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
        assert r.status_code == 401 and r.json()["code"] == "claude_login_required"
        assert client.get("/api/auth/status").json() == {"logged_in": False}

    client, _ = make_client()
    with client:
        first = client.post("/api/scrape").json()["job_id"]
        second = client.post("/api/scrape").json()["job_id"]
        assert first == second
        wait_job(client, first)
        assert client.get("/api/scrape/nope").status_code == 404
        assert client.post("/api/scrape", params={"companies": ["zzz"]}).status_code == 400


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
