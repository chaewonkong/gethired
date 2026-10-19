import re
from typing import Any

from .coupang import ENGINEERING_RE
from .greenhouse import GreenhouseScraper

LOCATION_RE = re.compile(r"Seoul|Korea|Canada|Toronto")
SCIENTIST_RE = re.compile(r"scientist", re.I)
EOI_RE = re.compile(r"^\s*expression of interest", re.I)


class MolocoScraper(GreenhouseScraper):
    company = "moloco"
    display_name = "몰로코"
    careers_url = "https://www.moloco.com/company/careers"
    board = "moloco"
    expected_count = 6

    def keep(self, job: dict[str, Any]) -> bool:
        loc = (job.get("location") or {}).get("name") or ""
        title = job["title"]
        return (
            bool(LOCATION_RE.search(loc))
            and bool(ENGINEERING_RE.search(title) or SCIENTIST_RE.search(title))
            and not EOI_RE.match(title)
        )

    def category(self, job: dict[str, Any]) -> str | None:
        depts = job.get("departments") or []
        return depts[0]["name"] if depts else None

