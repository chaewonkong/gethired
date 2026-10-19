import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from . import auth, config, llm
from .llm import LOGIN_COMMAND, LLMAuthError, auth_message
from .matcher import Match, judge, to_row
from .profile import Profile, get_profile
from .repository import Repository, now_iso
from .scrapers import REGISTRY, RawPosting, Scraper, make_client

ProfileLoader = Callable[[Repository], Awaitable[Profile]]
Judge = Callable[[Profile, list[RawPosting]], Awaitable[tuple[list[Match], list[Any]]]]
LoggedIn = Callable[[str], Awaitable[bool]]

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None


class JobRunning(Exception):
    """다른 보유자가 락을 쥠"""


class LoginRequired(Exception):
    def __init__(self, provider: str):
        self.provider, self.login_command, self.message = provider, LOGIN_COMMAND[provider], auth_message(provider)
        super().__init__(self.message)


class NoTargets(Exception):
    """관심회사 0 또는 unknown company"""


@dataclass
class CompanyState:
    status: str = "pending"  # pending / running / done / failed / auth_required
    fetched: int = 0
    new: int = 0
    stored: int = 0
    excluded: int = 0
    deleted: int = 0
    error: str | None = None


@dataclass
class Job:
    id: str
    companies: dict[str, CompanyState]
    status: str = "running"  # running / done / auth_required / interrupted
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    cost_usd: float = 0.0
    provider: str | None = None
    error: str | None = None  # job 전체 실패 사유 (프로필 추출 실패 등)

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.id, "status": self.status, "provider": self.provider, "started_at": self.started_at,
                "finished_at": self.finished_at, "cost_usd": round(self.cost_usd, 4), "error": self.error,
                "companies": {c: vars(s) for c, s in self.companies.items()}}


class JobManager:
    def __init__(self, repo: Repository, scrapers: dict[str, type[Scraper]] | None = None,
                 profile_loader: ProfileLoader = get_profile, judge_fn: Judge = judge,
                 lock_path: Path | None = None, logged_in: LoggedIn = auth.is_logged_in):
        self.repo = repo
        self.scrapers = scrapers if scrapers is not None else REGISTRY
        self.profile_loader = profile_loader
        self.judge_fn = judge_fn
        self.logged_in = logged_in
        # 같은 DB를 쓰는 프로세스끼리 배타
        db_path = config.DB_PATH if repo.path == ":memory:" else Path(repo.path)
        self.lock_path = Path(lock_path or db_path.with_suffix(".lock"))
        self._lock = FileLock(self.lock_path, thread_local=False)
        self.jobs: dict[str, Job] = {}
        self.current: Job | None = None
        self._task: asyncio.Task | None = None

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def prepare(self, companies: list[str] | None = None, logged_in: LoggedIn | None = None) -> list[str]:
        provider = llm.resolve_provider(self.repo.get_setting("provider"))
        if not await (logged_in or self.logged_in)(provider):
            raise LoginRequired(provider)
        unknown = [c for c in companies or [] if c not in self.scrapers]
        if unknown:
            raise NoTargets(f"unknown companies: {unknown}")
        targets = companies or [c for c in self.repo.list_interests() if c in self.scrapers]
        if not targets:
            raise NoTargets("no interest companies")
        return targets

    def start(self, targets: list[str]) -> Job:
        # FileLock은 같은 인스턴스의 재획득을 허용하므로 먼저 검사
        if self._lock.is_locked:
            raise JobRunning("이미 스크래핑 중입니다.")
        try:
            self._lock.acquire(timeout=0)
        except Timeout:
            raise JobRunning("다른 곳에서 스크래핑 중입니다.") from None
        try:
            names = [c for c in self.scrapers if c in targets]
            job = Job(id=uuid.uuid4().hex[:12], companies={c: CompanyState() for c in names})
            self._task = asyncio.create_task(self._run(job))
        except BaseException:
            self._lock.release()
            raise
        self.jobs[job.id] = job
        self.current = job
        return job

    async def run(self, targets: list[str]) -> Job:
        job = self.start(targets)
        await self._task
        return job

    def is_locked(self) -> bool:
        if self._lock.is_locked:
            return True
        if fcntl is None:  # 미검증
            probe = FileLock(self.lock_path, thread_local=False)
            try:
                probe.acquire(timeout=0)
            except Timeout:
                return True
            probe.release()
            return False
        # 락 파일을 만들거나 쓰지 않는다 (쓰기 불가 디렉토리에서도 동작)
        try:
            fd = os.open(self.lock_path, os.O_RDONLY)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(fd)
        return False

    async def _run(self, job: Job) -> None:
        try:
            await self._execute(job)
        except asyncio.CancelledError:
            job.status, job.finished_at = "interrupted", now_iso()
            raise
        finally:
            self._lock.release()

    async def _execute(self, job: Job) -> None:
        # job 전체는 시작 시점의 provider로 고정 (실행 중 PUT /api/settings/provider는 409)
        job.provider = llm.resolve_provider(self.repo.get_setting("provider"))
        llm.configure(job.provider)
        auth_failed = asyncio.Event()
        try:
            profile = await self.profile_loader(self.repo)
        except LLMAuthError:
            for s in job.companies.values():
                s.status = "auth_required"
            job.status, job.finished_at = "auth_required", now_iso()
            return
        except Exception as e:  # noqa: BLE001
            job.error = f"profile: {type(e).__name__}: {e}"[:200]
            for s in job.companies.values():
                s.status, s.error = "failed", job.error
            job.status, job.finished_at = "done", now_iso()
            return

        await asyncio.gather(*(self._run_company(job, c, profile, auth_failed) for c in job.companies))
        job.status = "auth_required" if auth_failed.is_set() else "done"
        job.finished_at = now_iso()

    async def _run_company(self, job: Job, company: str, profile: Profile, auth_failed: asyncio.Event) -> None:
        state = job.companies[company]
        state.status = "running"
        now = now_iso()
        run_id = self.repo.start_run(company, now)
        try:
            async with make_client() as client:
                postings = await self.scrapers[company]().fetch(client)
            if not postings:
                raise RuntimeError("0 postings (schema change?)")
            state.fetched = len(postings)
            ids = {p.external_id for p in postings}
            self.repo.mark_seen(company, ids, now)
            state.deleted = self.repo.soft_delete_missing(company, ids, now)

            judged = self.repo.judged_ids(company)
            new = [p for p in postings if p.external_id not in judged]
            state.new = len(new)
            if auth_failed.is_set():
                raise LLMAuthError("session expired during job")
            matches, results = await self.judge_fn(profile, new)
            job.cost_usd += sum(getattr(r, "cost_usd", 0.0) for r in results)

            by_id = {p.external_id: p for p in new}
            rows = [to_row(by_id[m.external_id], m, now) for m in matches if m.stored]
            self.repo.upsert_postings(rows)
            self.repo.record_judgments(company, [m.external_id for m in matches], {r["external_id"] for r in rows}, now)
            state.stored, state.excluded = len(rows), sum(1 for m in matches if not m.stored)
            state.status = "done"
            self.repo.finish_run(run_id, "done", now_iso(), fetched_count=len(postings))
        except asyncio.CancelledError:
            state.status, state.error = "failed", "interrupted"
            self.repo.finish_run(run_id, "failed", now_iso(), error="interrupted")
            raise
        except LLMAuthError as e:
            auth_failed.set()
            state.status, state.error = "auth_required", str(e)
            self.repo.finish_run(run_id, "auth_required", now_iso(), error=str(e)[:200], fetched_count=state.fetched or None)
        except Exception as e:  # noqa: BLE001
            state.status, state.error = "failed", f"{type(e).__name__}: {e}"[:200]
            self.repo.finish_run(run_id, "failed", now_iso(), error=state.error)
