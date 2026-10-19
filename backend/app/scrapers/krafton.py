"""크래프톤: 스튜디오별 Greenhouse 보드를 순회 (국내 · Tech/IT Infra/Data)."""
from typing import Any

import httpx

from .base import RawPosting
from .greenhouse import GreenhouseScraper, metadata

BOARDS = (
    "krafton",
    "pubgcorporation",
    "bluehole",
    "loonshotgames",
    "overdare",
    "omnicraftlabs",
    "relugames",
    "flywaygames",
    "risingwings",
    "9b_studio",
    "5minlab",
    "jofsoft",
    "ludorobotics",
    "inzoistudio",
)
KOREA = ("seoul", "pangyo", "bundang", "korea")
TECH_DEPARTMENTS = {"Tech", "IT Infra", "Data"}


def board_url(board: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def tech_department(job: dict[str, Any]) -> str | None:
    return next((d["name"] for d in job.get("departments") or [] if d.get("name") in TECH_DEPARTMENTS), None)


class KraftonScraper(GreenhouseScraper):
    company = "krafton"
    display_name = "크래프톤"
    careers_url = "https://www.krafton.com/careers/jobs/"
    board = "krafton"
    expected_count = 40

    def keep(self, job: dict[str, Any]) -> bool:
        loc = ((job.get("location") or {}).get("name") or "").lower()
        return any(k in loc for k in KOREA) and tech_department(job) is not None

    def category(self, job: dict[str, Any]) -> str | None:
        meta = metadata(job)
        dept = tech_department(job) or ""
        studio = meta.get("Corp./Studios") or self.board
        return f"{studio}/{meta.get(f'Job Category - {dept}') or dept}"


    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for board in BOARDS:
            r = await client.get(board_url(board))
            r.raise_for_status()
            postings.extend(self.parse(r.json()))
        return postings
