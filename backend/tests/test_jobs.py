import asyncio
import os
import select
import subprocess
import sys
from typing import ClassVar

import httpx
import pytest
from filelock import FileLock, Timeout

from app.jobs import JobManager, JobRunning, LoginRequired, NoTargets
from app.matcher import Breakdown, Match
from app.profile import Preferences, Profile
from app.repository import Repository
from app.scrapers import RawPosting, Scraper

PROFILE = Profile(name="t", seniority="mid", years_experience=5, core_skills=["Go"], familiar_skills=[],
                  weak_or_learning=[], domains=[], notable_achievements=[],
                  preferences=Preferences(locations=[], visa_or_work_authorization=None, target_domains=[], target_roles=[]),
                  dealbreakers=[], summary="s")


class Fake(Scraper):
    display_name: ClassVar[str] = "fake"
    careers_url: ClassVar[str] = "https://x"
    expected_count: ClassVar[int] = 1

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        return [RawPosting(company=self.company, external_id="1", title="Backend", apply_url="https://x/1",
                           description="d" * 200)]


class A(Fake, register=False):
    company = "a"


class B(Fake, register=False):
    company = "b"


def make_judge(delay: float = 0.0, started: list | None = None):
    async def judge(profile, postings):
        if started is not None:
            started.append(postings[0].company)
        await asyncio.sleep(delay)
        return [Match(external_id=p.external_id, fit_level="strong", score=90, gaps=[], summary="summary text",
                      tech_stack=[], fit_reason="reason " * 5, requirements=[], preferred=[],
                      breakdown=Breakdown(skills=35, domain=35, seniority=15, preferred=5)) for p in postings], []
    return judge


async def load_profile(repo):
    return PROFILE


def make_jobs(tmp_path, judge=None, logged_in=True, interests=("a", "b")) -> JobManager:
    repo = Repository()
    repo.set_interests(list(interests), "T0")

    async def is_logged_in(provider):
        return logged_in

    return JobManager(repo, scrapers={"a": A, "b": B}, profile_loader=load_profile, judge_fn=judge or make_judge(),
                      lock_path=tmp_path / "app.lock", logged_in=is_logged_in)


def free(path) -> bool:
    lock = FileLock(path)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return False
    lock.release()
    return True


def test_run_waits_for_completion(tmp_path):
    jobs = make_jobs(tmp_path)
    job = asyncio.run(jobs.run(["a", "b"]))
    assert job.status == "done" and job.finished_at and job.error is None
    assert {s.status for s in job.companies.values()} == {"done"}
    assert job.to_dict()["error"] is None
    assert not jobs.is_locked() and free(tmp_path / "app.lock")


def strip_to_legacy(repo: Repository) -> int:
    repo.conn.execute("UPDATE postings SET description=NULL, requirements=NULL, preferred=NULL, breakdown=NULL")
    repo.conn.commit()
    return repo.conn.execute("SELECT id FROM postings WHERE company='a'").fetchone()[0]


def test_legacy_posting_is_rejudged_and_filled(tmp_path):
    jobs = make_jobs(tmp_path)
    asyncio.run(jobs.run(["a"]))
    pid = strip_to_legacy(jobs.repo)

    seen: list[str] = []
    inner = make_judge()

    async def judge(profile, postings):
        seen.extend(p.external_id for p in postings)
        return await inner(profile, postings)

    jobs.judge_fn = judge
    asyncio.run(jobs.run(["a"]))
    assert seen == ["1"]
    p = jobs.repo.get_posting(pid)
    assert p["breakdown"] == {"skills": 35, "domain": 35, "seniority": 15, "preferred": 5}
    assert p["description"] == "d" * 200

    seen.clear()
    asyncio.run(jobs.run(["a"]))
    assert seen == []


def test_rejudged_exclude_hard_deletes_with_bookmark_and_feedback(tmp_path):
    jobs = make_jobs(tmp_path)
    asyncio.run(jobs.run(["a"]))
    pid = strip_to_legacy(jobs.repo)
    jobs.repo.set_bookmark(pid, True, "T1")
    jobs.repo.set_hidden(pid, True, "T1")
    jobs.repo.set_feedback(pid, "h", ["a: b"], "T1")
    jobs.repo.set_application(pid, "T1")

    async def exclude(profile, postings):
        return [Match(external_id=p.external_id, fit_level="exclude", score=10, gaps=[], summary="summary text",
                      tech_stack=[], fit_reason="reason " * 5, requirements=[], preferred=[],
                      breakdown=Breakdown(skills=10, domain=0, seniority=0, preferred=0)) for p in postings], []

    jobs.judge_fn = exclude
    job = asyncio.run(jobs.run(["a"]))
    assert job.companies["a"].excluded == 1 and job.companies["a"].stored == 0
    conn = jobs.repo.conn
    assert conn.execute("SELECT count(*) FROM postings WHERE id=?", (pid,)).fetchone()[0] == 0
    for table in ("bookmarks", "hides", "feedbacks", "applications"):
        assert conn.execute(f"SELECT count(*) FROM {table} WHERE posting_id=?", (pid,)).fetchone()[0] == 0, table
    assert jobs.repo.judged_ids("a") == {"1"}


def test_profile_failure_sets_job_error(tmp_path):
    jobs = make_jobs(tmp_path)

    async def broken(repo):
        raise ValueError("bad resume")

    jobs.profile_loader = broken
    job = asyncio.run(jobs.run(["a"]))
    assert job.error == "profile: ValueError: bad resume"
    assert job.to_dict()["error"] == job.error
    assert not jobs.is_locked()


def test_prepare_login_and_targets(tmp_path):
    with pytest.raises(LoginRequired) as e:
        asyncio.run(make_jobs(tmp_path, logged_in=False).prepare())
    assert (e.value.provider, e.value.login_command) == ("claude", "claude login")
    assert "`claude login`" in e.value.message

    jobs = make_jobs(tmp_path)
    assert asyncio.run(jobs.prepare()) == ["a", "b"]
    assert asyncio.run(jobs.prepare(["b"])) == ["b"]
    with pytest.raises(NoTargets):
        asyncio.run(jobs.prepare(["zzz"]))
    with pytest.raises(NoTargets):
        asyncio.run(make_jobs(tmp_path, interests=()).prepare())


def test_start_reentry_raises_job_running(tmp_path):
    jobs = make_jobs(tmp_path, judge=make_judge(0.1))

    async def main():
        job = jobs.start(["a"])
        assert jobs.is_locked()
        with pytest.raises(JobRunning):
            jobs.start(["b"])
        assert list(jobs.jobs) == [job.id]
        await jobs._task
        return job

    assert asyncio.run(main()).status == "done"
    assert not jobs.is_locked()


def test_start_fails_when_other_holder(tmp_path):
    jobs = make_jobs(tmp_path)
    with FileLock(tmp_path / "app.lock"):
        with pytest.raises(JobRunning):
            asyncio.run(jobs.run(["a"]))
        assert jobs.jobs == {} and jobs.current is None


def test_is_locked_paths_without_writing(tmp_path):
    lock_path = tmp_path / "app.lock"
    jobs = make_jobs(tmp_path, judge=make_judge(0.1))
    assert not jobs.is_locked()
    assert not lock_path.exists()

    async def main():
        jobs.start(["a"])
        assert jobs.is_locked()
        await jobs._task

    asyncio.run(main())
    assert not jobs.is_locked()

    other = FileLock(lock_path)
    with other:
        before = (lock_path.stat().st_mtime_ns, lock_path.read_bytes())
        assert jobs.is_locked()
        assert (lock_path.stat().st_mtime_ns, lock_path.read_bytes()) == before
    assert not jobs.is_locked()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_is_locked_in_readonly_dir(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    empty = make_jobs(d)
    held = FileLock(tmp_path / "held" / "app.lock")
    (tmp_path / "held").mkdir()
    held.acquire()
    probe = make_jobs(tmp_path / "held")
    os.chmod(d, 0o555)
    os.chmod(tmp_path / "held", 0o555)
    try:
        assert not empty.is_locked()
        assert list(d.iterdir()) == []
        assert probe.is_locked()
        held.release()
        assert not probe.is_locked()
        assert [p.name for p in (tmp_path / "held").iterdir()] == ["app.lock"]
    finally:
        os.chmod(d, 0o755)
        os.chmod(tmp_path / "held", 0o755)


def test_cancel_marks_runs_interrupted_and_releases(tmp_path):
    started: list[str] = []
    jobs = make_jobs(tmp_path, judge=make_judge(30, started))

    async def main():
        task = asyncio.create_task(jobs.run(["a", "b"]))
        async with asyncio.timeout(5):
            while len(started) < 2:
                await asyncio.sleep(0.01)
        assert jobs.is_locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    job = jobs.current
    assert job.status == "interrupted" and job.finished_at
    assert {(s.status, s.error) for s in job.companies.values()} == {("failed", "interrupted")}
    runs = [tuple(r) for r in jobs.repo.conn.execute("SELECT status, error FROM scrape_runs").fetchall()]
    assert runs == [("failed", "interrupted")] * 2
    assert not jobs.is_locked() and free(tmp_path / "app.lock")


def test_cancel_before_first_step_releases(tmp_path):
    jobs = make_jobs(tmp_path, judge=make_judge(30, []))

    async def main():
        job = jobs.start(["a", "b"])
        jobs._task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await jobs._task
        return job

    job = asyncio.run(main())
    assert job.status == "interrupted" and job.finished_at
    assert not jobs.is_locked() and free(tmp_path / "app.lock")


CHILD = """
import sys, time
from filelock import FileLock
lock = FileLock(sys.argv[1])
lock.acquire()
print("ready", flush=True)
time.sleep(60)
"""


def test_lock_released_when_holder_crashes(tmp_path):
    lock_path = tmp_path / "app.lock"
    proc = subprocess.Popen([sys.executable, "-c", CHILD, str(lock_path)], stdout=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([proc.stdout], [], [], 10)
        assert ready and proc.stdout.readline().strip() == "ready"
        assert not free(lock_path)
        assert make_jobs(tmp_path).is_locked()
        proc.kill()
        proc.wait(timeout=10)
        assert free(lock_path)
        assert not make_jobs(tmp_path).is_locked()
    finally:
        proc.kill()
        proc.wait(timeout=10)
