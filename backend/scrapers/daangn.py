from datetime import date
from typing import Any

from .base import parse_date
from .greenhouse import GreenhouseScraper, metadata


class DaangnScraper(GreenhouseScraper):
    company = "daangn"
    display_name = "당근"
    careers_url = "https://about.daangn.com/jobs/"
    board = "daangn"
    expected_count = 34

    def keep(self, job: dict[str, Any]) -> bool:
        return metadata(job).get("Division") == "Tech"

    def category(self, job: dict[str, Any]) -> str | None:
        return metadata(job).get("Division")

    def deadline(self, job: dict[str, Any]) -> date | None:
        return parse_date(metadata(job).get("Valid Through"), "%Y-%m-%d")
