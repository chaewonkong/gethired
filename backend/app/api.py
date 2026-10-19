from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import auth, resume
from .config import RESUME_DIR
from .jobs import JobManager, JobRunning, LoginRequired, NoTargets
from .llm import LOGIN_COMMAND, PROVIDERS, resolve_provider
from .repository import Repository, now_iso


class InterestsBody(BaseModel):
    companies: list[str]


class ProviderBody(BaseModel):
    provider: str


def create_app(repo: Repository, jobs: JobManager,
               logged_in: Callable[[str], Awaitable[bool]] = auth.is_logged_in,
               resume_dir: Path = RESUME_DIR) -> FastAPI:
    app = FastAPI(title="gethired")
    api = APIRouter(prefix="/api")

    def provider_setting() -> dict:
        stored = repo.get_setting("provider")
        return {"provider": resolve_provider(stored), "chosen": stored is not None}

    async def auth_status_body() -> dict:
        provider = provider_setting()["provider"]
        return {"provider": provider, "logged_in": await logged_in(provider), "login_command": LOGIN_COMMAND[provider]}

    @api.get("/settings/provider")
    def get_provider():
        return provider_setting()

    @api.put("/settings/provider")
    async def put_provider(body: ProviderBody):
        if body.provider not in PROVIDERS:
            raise HTTPException(status_code=400, detail=f"unknown provider: {body.provider}")
        if jobs.is_locked():
            return JSONResponse(status_code=409, content={"code": "job_running",
                                                          "message": "스크래핑 중에는 AI를 바꿀 수 없습니다."})
        repo.set_setting("provider", body.provider, now_iso())
        return await auth_status_body()

    @api.get("/auth/status")
    async def auth_status():
        return await auth_status_body()

    @api.get("/companies")
    def companies():
        last = repo.last_runs()
        interests = set(repo.list_interests())
        return [
            {"company": name, "display_name": cls.display_name, "careers_url": cls.careers_url,
             "last_run": last.get(name), "interested": name in interests}
            for name, cls in jobs.scrapers.items()
        ]

    def check_known(companies: list[str]) -> None:
        unknown = [c for c in companies if c not in jobs.scrapers]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown companies: {unknown}")

    @api.put("/interests")
    def put_interests(body: InterestsBody):
        if not body.companies:
            raise HTTPException(status_code=400, detail="at least one company is required")
        check_known(body.companies)
        repo.set_interests(body.companies, now_iso())
        return {"companies": repo.list_interests()}

    def interest(company: str, on: bool):
        check_known([company])
        repo.set_interest(company, on, now_iso())
        return {"company": company, "interested": on}

    @api.put("/companies/{company}/interest")
    def add_interest(company: str):
        return interest(company, True)

    @api.delete("/companies/{company}/interest")
    def remove_interest(company: str):
        return interest(company, False)

    @api.post("/scrape", status_code=202)
    async def scrape(companies: list[str] | None = Query(default=None)):
        if jobs.current and jobs.current.status == "running":
            return {"job_id": jobs.current.id, "status": "running"}
        try:
            targets = await jobs.prepare(companies, logged_in=logged_in)
        except LoginRequired as e:
            return JSONResponse(status_code=401, content={"code": "login_required", "provider": e.provider,
                                                          "message": e.message, "login_command": e.login_command})
        except NoTargets as e:
            raise HTTPException(status_code=400, detail=str(e))
        try:
            job = jobs.start(targets)
        except JobRunning as e:
            return JSONResponse(status_code=409, content={"code": "job_running", "message": str(e)})
        return {"job_id": job.id, "status": job.status}

    @api.get("/scrape/{job_id}")
    def scrape_status(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @api.get("/postings")
    def postings(company: str | None = None, min_level: Literal["stretch", "good", "strong"] | None = None):
        return repo.list_postings(company=company, min_level=min_level)

    def bookmark(posting_id: int, on: bool):
        if not repo.set_bookmark(posting_id, on, now_iso()):
            raise HTTPException(status_code=404, detail="posting not found")
        return {"posting_id": posting_id, "bookmarked": on}

    @api.put("/postings/{posting_id}/bookmark")
    def add_bookmark(posting_id: int):
        return bookmark(posting_id, True)

    @api.delete("/postings/{posting_id}/bookmark")
    def remove_bookmark(posting_id: int):
        return bookmark(posting_id, False)

    def hide(posting_id: int, on: bool):
        if not repo.set_hidden(posting_id, on, now_iso()):
            raise HTTPException(status_code=404, detail="posting not found")
        return {"posting_id": posting_id, "hidden": on}

    @api.put("/postings/{posting_id}/hide")
    def add_hide(posting_id: int):
        return hide(posting_id, True)

    @api.delete("/postings/{posting_id}/hide")
    def remove_hide(posting_id: int):
        return hide(posting_id, False)

    @api.get("/resume")
    def resume_files():
        return resume.list_files(resume_dir)

    @api.put("/resume/{name}")
    async def put_resume(name: str, request: Request):
        try:
            await resume.save(resume_dir, name, request.stream())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {}

    @api.delete("/resume/{name}")
    def delete_resume(name: str):
        try:
            found = resume.delete(resume_dir, name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not found:
            raise HTTPException(status_code=404, detail="resume file not found")
        return {"name": name}

    app.include_router(api)
    return app
