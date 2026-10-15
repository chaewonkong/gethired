from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# 카카오뱅크 인재영입. recruit.kakaobank.com은 Next.js 프론트이고 목록은 POST /api/recruits(페이지네이션), 상세는 GET /api/recruits/{sn}.
# 지원 자체는 kakaobank.recruiter.co.kr로 넘어가지만 공고 페이지(/jobs/{sn})를 apply_url로 쓴다.
LIST_URL = "https://recruit.kakaobank.com/api/recruits"
DETAIL_URL = "https://recruit.kakaobank.com/api/recruits/{sn}"
VIEW_URL = "https://recruit.kakaobank.com/jobs/{sn}"
HEADERS = {"Accept": "application/json"}
TECH_CLASSES = {"AI", "Core Banking", "Data", "Engineering", "Security", "Server"}


def keep(job: dict[str, Any]) -> bool:
    return job.get("recruitClassName") in TECH_CLASSES


def to_posting(job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    sn = job["recruitNoticeSn"]
    return RawPosting(
        company="kakaobank",
        external_id=str(sn),
        title=job["recruitNoticeName"].strip(),
        apply_url=VIEW_URL.format(sn=sn),
        deadline=parse_date(job.get("receiveEndDatetime"), "%Y-%m-%d"),
        description=html_to_text(detail.get("contents")),
        category=job.get("recruitClassName"),
        raw=detail,
    )


class KakaoBankScraper(Scraper):
    company = "kakaobank"
    display_name = "카카오뱅크"
    careers_url = "https://recruit.kakaobank.com/jobs"
    expected_count = 22

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        page = 1
        while True:
            r = await client.post(LIST_URL, json={"pageNumber": page}, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            for job in data["list"]:
                if not keep(job):
                    continue
                d = await client.get(DETAIL_URL.format(sn=job["recruitNoticeSn"]), headers=HEADERS)
                d.raise_for_status()
                out.append(to_posting(job, d.json()))
            if page >= int(data["paging"].get("totalPages") or 1):
                break
            page += 1
        return out
