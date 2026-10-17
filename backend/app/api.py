from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import auth, resume
from .config import RESUME_DIR
from .jobs import JobManager
from .llm import auth_message, current_provider
from .repository import Repository, now_iso


class ResumeBody(BaseModel):
    content: str


class InterestsBody(BaseModel):
    companies: list[str]


def create_app(repo: Repository, jobs: JobManager,
               logged_in: Callable[[], Awaitable[bool]] = auth.is_logged_in,
               resume_dir: Path = RESUME_DIR) -> FastAPI:
    app = FastAPI(title="job-posting")
    api = APIRouter(prefix="/api")

    @api.get("/auth/status")
    async def auth_status():
        return {"logged_in": await logged_in()}

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
        if not await logged_in():
            return JSONResponse(status_code=401, content={"code": "claude_login_required",
                                                          "message": auth_message(current_provider())})
        check_known(companies or [])
        targets = companies or [c for c in repo.list_interests() if c in jobs.scrapers]
        if not targets:
            raise HTTPException(status_code=400, detail="no interest companies")
        job = jobs.start(targets)
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
    def put_resume(name: str, body: ResumeBody):
        try:
            resume.save(resume_dir, name, body.content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"name": name}

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
