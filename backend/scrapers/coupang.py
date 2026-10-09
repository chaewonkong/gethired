import re
from typing import Any

from .greenhouse import GreenhouseScraper

ENGINEERING_RE = re.compile(
    r"engineer|developer|back-?end|front-?end|software|\bsre\b|devops|infra|platform"
    r"|machine learning|data|security|architect|개발",
    re.I,
)


class CoupangScraper(GreenhouseScraper):
    company = "coupang"
    display_name = "쿠팡"
    careers_url = "https://www.coupang.jobs/kr/"
    board = "coupang"
    expected_count = 95

    def keep(self, job: dict[str, Any]) -> bool:
        loc = (job.get("location") or {}).get("name") or ""
        return "Korea" in loc and bool(ENGINEERING_RE.search(job["title"]))

    def category(self, job: dict[str, Any]) -> str | None:
        return "title-keyword"
