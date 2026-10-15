from datetime import date
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# 우아한형제들 인재영입. 목록·상세 모두 공개 JSON API. 상세는 recruitSeq가 아니라 recruitNumber(R2605009)로 조회해야 한다.
LIST_URL = "https://career.woowahan.com/w1/recruits"
DETAIL_URL = "https://career.woowahan.com/w1/recruits/{number}"
VIEW_URL = "https://career.woowahan.com/recruitment/{number}/detail"
DEV_JOB_GROUP = "BA005001"
HEADERS = {"Accept": "application/json"}
PAGE_SIZE = 100


def deadline(s: str | None) -> date | None:
    d = parse_date(s, "%Y-%m-%d")
    return None if d is None or d.year >= 2999 else d  # 상시 채용은 2999/9999-12-31


def to_posting(job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    number = job["recruitNumber"]
    return RawPosting(
        company="woowahan",
        external_id=number,
        title=job["recruitName"].strip(),
        apply_url=VIEW_URL.format(number=number),
        deadline=deadline(job.get("recruitEndDate")),
        description=html_to_text(detail.get("recruitContents")),
        category=(job.get("jobGroup") or {}).get("recruitItemCode"),
        raw=detail,
    )


class WoowahanScraper(Scraper):
    company = "woowahan"
    display_name = "우아한형제들"
    careers_url = "https://career.woowahan.com/"
    expected_count = 7

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        page = 0
        while True:
            r = await client.get(LIST_URL, params={"jobGroupCodes": DEV_JOB_GROUP, "page": page, "size": PAGE_SIZE,
                                                   "sort": "updateDate,desc"}, headers=HEADERS)
            r.raise_for_status()
            data = r.json()["data"]
            for job in data["list"]:
                d = await client.get(DETAIL_URL.format(number=job["recruitNumber"]), headers=HEADERS)
                d.raise_for_status()
                out.append(to_posting(job, d.json()["data"]))
            if page + 1 >= int(data.get("totalPageNumber") or 1):
                break
            page += 1
        return out
