from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

LIST_URL = "https://careers.kakao.com/public/api/job-list"


def to_posting(job: dict[str, Any]) -> RawPosting:
    parts = [html_to_text(job.get(k)) for k in ("introduction", "workContentDesc", "qualification")]
    return RawPosting(
        company="kakao",
        external_id=job["realId"],
        title=job["jobOfferTitle"].strip(),
        apply_url=f"https://careers.kakao.com/jobs/{job['realId']}",
        deadline=parse_date(job.get("endDate"), "%Y-%m-%d"),
        description="\n".join(p for p in parts if p) or None,
        category=f"{job.get('jobType')}/{job.get('jobPartName')}",
        raw=job,
    )


def parse_page(data: dict[str, Any]) -> list[RawPosting]:
    return [to_posting(j) for j in data.get("jobList", [])]


class KakaoScraper(Scraper):
    company = "kakao"
    display_name = "카카오"
    careers_url = "https://careers.kakao.com/jobs"
    expected_count = 33

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        page = 1
        while True:
            r = await client.get(LIST_URL, params={"company": "ALL", "part": "TECHNOLOGY", "page": page})
            r.raise_for_status()
            data = r.json()
            out += parse_page(data)
            if page >= int(data.get("totalPage") or 1):
                break
            page += 1
        return out
