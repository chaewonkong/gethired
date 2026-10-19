import re
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date
from .greetinghr import parse_opening_info

# 오늘의집(버킷플레이스) 채용. www.bucketplace.com/careers는 Gatsby 정적 사이트이고 목록은 page-data.json의
# result.data.position.nodes[].frontmatter에 있다. 상세는 GreetingHR 공고 페이지(/ko/o/{id})를 쓴다.
# GreetingHR 루트 페이지는 404라 GreetingHRScraper.fetch는 쓸 수 없다.
LIST_URL = "https://www.bucketplace.com/page-data/careers/page-data.json"
DETAIL_URL = "https://bucketplace.career.greetinghr.com/ko/o/{id}"
KEEP_TEAMS = {"Engineering"}
_ID_RE = re.compile(r"/o/(\d+)")


def parse_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [n["frontmatter"] for n in data["result"]["data"]["position"]["nodes"]]


def keep(job: dict[str, Any]) -> bool:
    return job.get("teamName") in KEEP_TEAMS


def opening_id(job: dict[str, Any]) -> str | None:
    m = _ID_RE.search(job.get("recruitUrl") or "")
    return m.group(1) if m else None


def to_posting(job: dict[str, Any], info: dict[str, Any]) -> RawPosting:
    oid = opening_id(job)
    team, hiring = job.get("teamName"), job.get("hiringType")
    return RawPosting(
        company="bucketplace",
        external_id=oid,
        title=job["name"].strip(),
        apply_url=DETAIL_URL.format(id=oid),
        deadline=parse_date(info.get("dueDate"), "%Y-%m-%d"),
        description=html_to_text(info.get("detail")),
        category=f"{team}/{hiring}" if hiring else team,
        raw=info,
    )


class BucketplaceScraper(Scraper):
    company = "bucketplace"
    display_name = "오늘의집"
    careers_url = "https://www.bucketplace.com/careers/"
    expected_count = 14

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(LIST_URL)
        r.raise_for_status()
        out: list[RawPosting] = []
        for job in parse_list(r.json()):
            if not keep(job) or (oid := opening_id(job)) is None:
                continue
            d = await client.get(DETAIL_URL.format(id=oid))
            d.raise_for_status()
            out.append(to_posting(job, parse_opening_info(d.text)))
        return out
