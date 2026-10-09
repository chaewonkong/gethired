from datetime import date
from typing import Any, ClassVar

import httpx

from .base import RawPosting, Scraper, html_to_text


def metadata(job: dict[str, Any]) -> dict[str, Any]:
    return {m["name"]: m.get("value") for m in job.get("metadata") or []}


class GreenhouseScraper(Scraper):
    board: ClassVar[str]

    @property
    def list_url(self) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs?content=true"

    def unwrap(self, data: Any) -> list[dict[str, Any]]:
        return data["jobs"]

    def keep(self, job: dict[str, Any]) -> bool:
        return True

    def category(self, job: dict[str, Any]) -> str | None:
        return None

    def description(self, job: dict[str, Any]) -> str | None:
        return html_to_text(job.get("content"))

    def deadline(self, job: dict[str, Any]) -> date | None:
        return None

    def parse(self, data: Any) -> list[RawPosting]:
        return [
            RawPosting(
                company=self.company,
                external_id=str(job["id"]),
                title=job["title"].strip(),
                apply_url=job["absolute_url"],
                deadline=self.deadline(job),
                description=self.description(job),
                category=self.category(job),
                raw=job,
            )
            for job in self.unwrap(data)
            if self.keep(job)
        ]

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(self.list_url)
        r.raise_for_status()
        return self.parse(r.json())
