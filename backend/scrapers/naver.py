import asyncio
import re
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

LIST_URL = "https://recruit.navercorp.com/rcrt/loadJobList.do"
VIEW_URL = "https://recruit.navercorp.com/rcrt/view.do"
PAGE_SIZE = 10
_DETAIL_RE = re.compile(r'<div class="detail_wrap">(.*?)<div class="(?:card_apply|btn_area|apply)', re.S)
_BOX_RE = re.compile(r'<div class="detail_box">(.*?)</div>\s*</div>', re.S)


def parse_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [j for j in data.get("list", []) if j.get("classCdNm") == "Tech"]


def parse_detail(html: str) -> str | None:
    m = _DETAIL_RE.search(html)
    seg = m.group(1) if m else html
    boxes = _BOX_RE.findall(seg)
    text = "\n".join(filter(None, (html_to_text(b) for b in boxes)))
    return text or None


def to_posting(job: dict[str, Any], description: str | None) -> RawPosting:
    return RawPosting(
        company="naver",
        external_id=str(job["annoId"]),
        title=job["annoSubject"].strip(),
        apply_url=job.get("jobDetailLink") or f"{VIEW_URL}?annoId={job['annoId']}",
        deadline=parse_date(job.get("endYmd"), "%Y%m%d"),
        description=description,
        category=f"{job.get('classCdNm')}/{job.get('subJobCdNm')}",
        raw=job,
    )


class NaverScraper(Scraper):
    company = "naver"
    display_name = "네이버"
    careers_url = "https://recruit.navercorp.com/rcrt/list.do"
    expected_count = 4

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        jobs: list[dict[str, Any]] = []
        first = 0
        while True:
            r = await client.get(LIST_URL, params={"firstIndex": first},
                                 headers={"X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status()
            data = r.json()
            jobs += parse_list(data)
            first += PAGE_SIZE
            if not data.get("list") or first >= int(data.get("totalSize") or 0):
                break

        sem = asyncio.Semaphore(5)

        async def detail(job: dict[str, Any]) -> RawPosting:
            async with sem:
                r = await client.get(VIEW_URL, params={"annoId": job["annoId"]})
                r.raise_for_status()
                return to_posting(job, parse_detail(r.text))

        return list(await asyncio.gather(*(detail(j) for j in jobs)))
