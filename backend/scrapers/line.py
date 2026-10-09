import asyncio
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

LIST_URL = "https://careers.linecorp.com/page-data/ko/jobs/page-data.json"
DETAIL_URL = "https://careers.linecorp.com/page-data/ko/jobs/{id}/page-data.json"
KOREA = 1


def parse_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [e["node"] for e in data["result"]["data"]["allStrapiJobs"]["edges"]]
    return [
        n for n in nodes
        if n.get("publish") and n.get("is_public", True)
        and any(c.get("country") == KOREA for c in n.get("cities") or [])
        and any(u.get("name") == "Engineering" for u in n.get("job_unit") or [])
    ]


def to_posting(node: dict[str, Any], detail: dict[str, Any] | None) -> RawPosting:
    job = (detail or {}).get("result", {}).get("data", {}).get("strapiJobs") or {}
    fields = ",".join(f["name"] for f in node.get("job_fields") or [])
    return RawPosting(
        company="line",
        external_id=str(node["strapiId"]),
        title=node["title"].strip(),
        apply_url=job.get("apply_link") or f"https://careers.linecorp.com/ko/jobs/{node['strapiId']}",
        deadline=None if node.get("until_filled") else parse_date(node.get("end_date"), "%Y-%m-%d"),
        description=html_to_text(job.get("content")),
        category=f"Engineering/{fields}",
        raw=node,
    )


class LineScraper(Scraper):
    company = "line"
    display_name = "라인"
    careers_url = "https://careers.linecorp.com/ko/jobs"
    expected_count = 12

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(LIST_URL)
        r.raise_for_status()
        nodes = parse_list(r.json())
        sem = asyncio.Semaphore(8)

        async def detail(node: dict[str, Any]) -> RawPosting:
            async with sem:
                r = await client.get(DETAIL_URL.format(id=node["strapiId"]))
                r.raise_for_status()
                return to_posting(node, r.json())

        return list(await asyncio.gather(*(detail(n) for n in nodes)))
