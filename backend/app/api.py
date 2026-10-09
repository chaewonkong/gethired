from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from . import auth
from .jobs import JobManager
from .llm import AUTH_MESSAGE
from .repository import Repository


def create_app(repo: Repository, jobs: JobManager,
               logged_in: Callable[[], Awaitable[bool]] = auth.is_logged_in) -> FastAPI:
    app = FastAPI(title="job-posting")
    api = APIRouter(prefix="/api")

    @api.get("/auth/status")
    async def auth_status():
        return {"logged_in": await logged_in()}

    @api.get("/companies")
    def companies():
        last = repo.last_runs()
        return [
            {"company": name, "display_name": cls.display_name, "careers_url": cls.careers_url,
             "last_run": last.get(name)}
            for name, cls in jobs.scrapers.items()
        ]

    @api.post("/scrape", status_code=202)
    async def scrape(companies: list[str] | None = Query(default=None)):
        if jobs.current and jobs.current.status == "running":
            return {"job_id": jobs.current.id, "status": "running"}
        if not await logged_in():
            return JSONResponse(status_code=401, content={"code": "claude_login_required", "message": AUTH_MESSAGE})
        unknown = [c for c in companies or [] if c not in jobs.scrapers]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown companies: {unknown}")
        job = jobs.start(companies)
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

    app.include_router(api)
    return app
