from datetime import date
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# NHN Careers. careers.nhn.com은 Vite SPA이고 같은 origin의 REST API를 쓴다.
# 목록은 GET /v1/job-postings(page는 0부터, size 미지정 시 30건, 전체 건수는 paging.totalSize), 상세는 GET /v1/job-postings/{id}.
# 계열사(NHN Cloud, NHN COMMERCE 등) 공고가 함께 나온다.
LIST_URL = "https://careers.nhn.com/v1/job-postings"
DETAIL_URL = "https://careers.nhn.com/v1/job-postings/{id}"
VIEW_URL = "https://careers.nhn.com/recruits/{id}"
PAGE_SIZE = 100
TECH_GROUP = "Tech"


def keep(job: dict[str, Any]) -> bool:
    return any(s["jobGroup"]["name"] == TECH_GROUP for s in job.get("jobSeries") or [])


def deadline(s: str | None) -> date | None:
    d = parse_date(s, "%Y-%m-%d")
    return None if d is None or d.year >= 2999 else d  # 상시 채용은 2999-12-31


def description(detail: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for item in detail.get("jobPostingContentsItems") or []:
        parts.append(item.get("title") or "")
        parts.extend(c for c in item.get("contents") or [] if isinstance(c, str))
        parts.append(item.get("footer") or "")
    return html_to_text("<br>".join(parts))


def to_posting(job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    series = dict.fromkeys(s["name"] for s in job["jobSeries"] if s["jobGroup"]["name"] == TECH_GROUP)
    return RawPosting(
        company="nhn",
        external_id=job["id"],
        title=job["name"].strip(),
        apply_url=VIEW_URL.format(id=job["id"]),
        deadline=deadline(job.get("postingEndDatetime")),
        description=description(detail),
        category=f"{job['corporation']['name']}/{'·'.join(series)}",
        raw=detail,
    )


class NHNScraper(Scraper):
    company = "nhn"
    display_name = "NHN"
    careers_url = "https://careers.nhn.com/recruits"
    expected_count = 34

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        page = 0
        while True:
            r = await client.get(LIST_URL, params={"page": page, "size": PAGE_SIZE})
            r.raise_for_status()
            data = r.json()
            for job in data["result"]:
                if not keep(job):
                    continue
                d = await client.get(DETAIL_URL.format(id=job["id"]))
                d.raise_for_status()
                out.append(to_posting(job, d.json()["result"]))
            page += 1
            if not data["result"] or page * PAGE_SIZE >= int(data["paging"]["totalSize"]):
                break
        return out
