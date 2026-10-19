from typing import Any, ClassVar

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# Ninehire 채용 페이지. 목록은 identity-access/homepage/recruitments(countPerPage·page 페이징, 전체 건수는 count),
# 본문은 recruiting/job-posting의 content(HTML). 지원 페이지(*.ninehire.site)는 Vercel checkpoint라 링크만 저장한다.
LIST_URL = "https://api.ninehire.com/identity-access/homepage/recruitments"
DETAIL_URL = "https://api.ninehire.com/recruiting/job-posting"
PAGE_SIZE = 100


def job_group(job: dict[str, Any]) -> str | None:
    return (job.get("jobGroup") or {}).get("title")


class NinehireScraper(Scraper):
    company_id: ClassVar[str]
    site: ClassVar[str]
    keep_groups: ClassVar[frozenset[str]]

    def keep(self, job: dict[str, Any]) -> bool:
        return job_group(job) in self.keep_groups and not job.get("isPrivate")

    def apply_url(self, job: dict[str, Any]) -> str:
        return f"https://{self.site}.ninehire.site/job_posting/{job['addressKey']}"

    def to_posting(self, job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
        return RawPosting(
            company=self.company,
            external_id=job["recruitmentId"],
            title=(job.get("externalTitle") or job["title"]).strip(),
            apply_url=self.apply_url(job),
            deadline=parse_date(job.get("deadlineValue"), "%Y-%m-%d"),
            description=html_to_text(detail.get("content")),
            category=job_group(job),
            raw=detail,
        )

    async def list_jobs(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while True:
            r = await client.get(
                LIST_URL, params={"companyId": self.company_id, "countPerPage": PAGE_SIZE, "page": page}
            )
            r.raise_for_status()
            data = r.json()
            jobs.extend(data["results"])
            page += 1
            if not data["results"] or len(jobs) >= int(data["count"]):
                return jobs

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        for job in await self.list_jobs(client):
            if not self.keep(job):
                continue
            d = await client.get(DETAIL_URL, params={"recruitmentId": job["recruitmentId"]})
            d.raise_for_status()
            out.append(self.to_posting(job, d.json()))
        return out
