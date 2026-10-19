import re
from typing import Any

import httpx

from .base import RawPosting, Scraper
from .greetinghr import page_props

# 래블업 채용 페이지(Next.js SSR). 목록은 /ko/careers의 __NEXT_DATA__ positions.contents,
# 상세는 /ko/careers/{positionId}의 positionDetail.jobDescriptions(마크다운 본문). 마감일 필드는 없다.
# 페이지당 sliceNumber(20)건이고 페이지 쿼리는 확인하지 못해 첫 페이지만 읽는다.
LIST_URL = "https://www.lablup.com/ko/careers"
VIEW_URL = "https://www.lablup.com/ko/careers/{id}"
KEEP_CATEGORIES = frozenset({"software-engineer", "FRONTEND", "CORE", "RESEARCH", "TRP", "SOLUTION"})
_BULLET_RE = re.compile(r"^(\s*)\*\s+", re.M)


def parse_list(html: str) -> list[dict[str, Any]]:
    return page_props(html)["positions"]["contents"]


def parse_detail(html: str) -> dict[str, Any]:
    return page_props(html)["positionDetail"]


def keep(job: dict[str, Any]) -> bool:
    return (job.get("category") or {}).get("categoryId") in KEEP_CATEGORIES


def description(detail: dict[str, Any]) -> str | None:
    parts = []
    for s in detail.get("jobDescriptions") or []:
        body = _BULLET_RE.sub(r"\1- ", (s.get("body") or "").strip())
        parts.append(f"{(s.get('title') or '').strip()}\n{body}".strip())
    return "\n\n".join(p for p in parts if p) or None


def to_posting(job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    category = job["category"]["categoryId"]
    level = (job.get("experienced") or {}).get("name")
    return RawPosting(
        company="lablup",
        external_id=job["positionId"],
        title=job["title"].strip(),
        apply_url=VIEW_URL.format(id=job["positionId"]),
        deadline=None,
        description=description(detail),
        category=f"{category}/{level}" if level else category,
        raw=detail,
    )


class LablupScraper(Scraper):
    company = "lablup"
    display_name = "래블업"
    careers_url = LIST_URL
    expected_count = 3

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(LIST_URL)
        r.raise_for_status()
        out: list[RawPosting] = []
        for job in parse_list(r.text):
            if not keep(job):
                continue
            d = await client.get(VIEW_URL.format(id=job["positionId"]))
            d.raise_for_status()
            out.append(to_posting(job, parse_detail(d.text)))
        return out
