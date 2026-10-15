from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text

# 하이퍼커넥트 채용 사이트는 Match Group의 Lever 보드를 Gatsby로 빌드한 것. Lever 공개 API에서 서울 포지션만 가져온다.
# Match Group 소속 서울 포지션(Match Group AI 등)도 포함하고, 구분은 category(department/team)에 보존한다.
LIST_URL = "https://api.lever.co/v0/postings/matchgroup?mode=json"


def keep(job: dict[str, Any]) -> bool:
    return "Seoul" in ((job.get("categories") or {}).get("location") or "")


def description(job: dict[str, Any]) -> str | None:
    parts = [job.get("descriptionPlain")]
    for lst in job.get("lists") or []:
        parts += [lst.get("text"), html_to_text(lst.get("content"))]
    parts.append(job.get("additionalPlain"))
    return "\n".join(p.strip() for p in parts if p and p.strip()) or None


def to_posting(job: dict[str, Any]) -> RawPosting:
    c = job.get("categories") or {}
    return RawPosting(
        company="hyperconnect",
        external_id=job["id"],
        title=job["text"].strip(),
        apply_url=job["hostedUrl"],
        description=description(job),
        category=f"{c.get('department')}/{c.get('team')}",
        raw=job,
    )


def parse(jobs: list[dict[str, Any]]) -> list[RawPosting]:
    return [to_posting(j) for j in jobs if keep(j)]


class HyperconnectScraper(Scraper):
    company = "hyperconnect"
    display_name = "하이퍼커넥트"
    careers_url = "https://career.hyperconnect.com/jobs"
    expected_count = 8

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(LIST_URL)
        r.raise_for_status()
        return parse(r.json())
