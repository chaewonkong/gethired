from typing import Any

import httpx

from .base import RawPosting, Scraper

# 42dot 채용 페이지는 Ashby 보드를 임베드한다. 공개 API에서 한국 근무지의 ENGINEERING 부서만 가져온다.
LIST_URL = "https://api.ashbyhq.com/posting-api/job-board/42dot"


def keep(job: dict[str, Any]) -> bool:
    return (job.get("isListed", True) and "South Korea" in (job.get("location") or "")
            and job.get("department") == "ENGINEERING")


def to_posting(job: dict[str, Any]) -> RawPosting:
    return RawPosting(
        company="42dot",
        external_id=job["id"],
        title=job["title"].strip(),
        apply_url=job["jobUrl"],
        description=(job.get("descriptionPlain") or "").strip() or None,
        category=f"{job.get('department')}/{job.get('team')}",
        raw=job,
    )


def parse(data: dict[str, Any]) -> list[RawPosting]:
    return [to_posting(j) for j in data["jobs"] if keep(j)]


class FortyTwoDotScraper(Scraper):
    company = "42dot"
    display_name = "42dot"
    careers_url = "https://42dot.ai/careers"
    expected_count = 45

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(LIST_URL)
        r.raise_for_status()
        return parse(r.json())
