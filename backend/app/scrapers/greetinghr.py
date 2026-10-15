import json
import re
from typing import Any, Callable, ClassVar

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# GreetingHR 채용 페이지(Next.js). 목록은 첫 페이지의 __NEXT_DATA__ dehydratedState["openings"],
# 본문은 공고 페이지(/ko/o/{id})의 getOpeningById 쿼리에 들어 있다. 별도 공개 API는 없다.
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def page_props(html: str) -> dict[str, Any]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ not found")
    return json.loads(m.group(1))["props"]["pageProps"]


def query_data(props: dict[str, Any], match: Callable[[list[Any]], bool]) -> Any:
    for q in props["dehydratedState"]["queries"]:
        if match(q["queryKey"]):
            return q["state"]["data"]
    raise KeyError("query not found")


def parse_openings(html: str) -> list[dict[str, Any]]:
    return query_data(page_props(html), lambda k: k == ["openings"])


def parse_opening_info(html: str) -> dict[str, Any]:
    data = query_data(page_props(html), lambda k: len(k) > 1 and k[1] == "getOpeningById")
    return data["data"]["openingsInfo"]


def occupations(opening: dict[str, Any]) -> set[str]:
    positions = (opening.get("openingJobPosition") or {}).get("openingJobPositions") or []
    return {(p.get("workspaceOccupation") or {}).get("occupation") or "?" for p in positions}


class GreetingHRScraper(Scraper):
    host: ClassVar[str]
    keep_occupations: ClassVar[frozenset[str]]

    def keep(self, opening: dict[str, Any]) -> bool:
        return bool(occupations(opening) & self.keep_occupations)

    def opening_url(self, opening_id: int | str) -> str:
        return f"https://{self.host}/ko/o/{opening_id}"

    def to_posting(self, opening: dict[str, Any], info: dict[str, Any]) -> RawPosting:
        return RawPosting(
            company=self.company,
            external_id=str(opening["openingId"]),
            title=opening["title"].strip(),
            apply_url=self.opening_url(opening["openingId"]),
            deadline=parse_date(info.get("dueDate"), "%Y-%m-%d"),
            description=html_to_text(info.get("detail")),
            category="/".join(sorted(occupations(opening))),
            raw=opening,
        )

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(f"https://{self.host}/")
        r.raise_for_status()
        out: list[RawPosting] = []
        for opening in parse_openings(r.text):
            if not self.keep(opening):
                continue
            d = await client.get(self.opening_url(opening["openingId"]))
            d.raise_for_status()
            out.append(self.to_posting(opening, parse_opening_info(d.text)))
        return out
