from datetime import date
from typing import Any

from .base import parse_date
from .greenhouse import GreenhouseScraper, metadata

ENGINEERING_CATEGORIES = {
    "Backend", "Infra", "Data Engineering", "ML", "Security Engineering", "Frontend", "QA",
}


def _meta_startswith(job: dict[str, Any], prefix: str) -> Any:
    for k, v in metadata(job).items():
        if k.startswith(prefix):
            return v
    return None


class TossScraper(GreenhouseScraper):
    company = "toss"
    display_name = "토스"
    careers_url = "https://toss.im/career/jobs"
    board = "toss"
    expected_count = 144

    @property
    def list_url(self) -> str:
        return "https://api-public.toss.im/api/v3/ipd-eggnog/career/jobs"

    def unwrap(self, data: Any) -> list[dict[str, Any]]:
        return data["success"]

    def keep(self, job: dict[str, Any]) -> bool:
        return self.category(job) in ENGINEERING_CATEGORIES

    def category(self, job: dict[str, Any]) -> str | None:
        return _meta_startswith(job, "커리어 페이지 노출 Job Category")

    def description(self, job: dict[str, Any]) -> str | None:
        v = _meta_startswith(job, "Job Description을 작성해 주세요")
        return v.strip() if isinstance(v, str) and v.strip() else None

    def deadline(self, job: dict[str, Any]) -> date | None:
        return parse_date(_meta_startswith(job, "커리어페이지 채용공고 클로징 일자"), "%Y-%m-%d")
