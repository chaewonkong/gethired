from typing import Any

import httpx

from .base import RawPosting, Scraper, parse_date

# 현대자동차 인재채용. 목록 API는 공개되어 있으나 상세(JD) API는 WAF(F5 ASM)가 비브라우저 요청을 400으로 막아
# 본문은 목록 메타데이터로만 구성한다. 지원 링크에서 전체 JD 확인 가능.
LIST_URL = "https://talent.hyundai.com/api/rec/AP-HM-FO-02700"
VIEW_URL = "https://talent.hyundai.com/apply/applyView.hc?recuYy={recuYy}&recuType={recuType}&recuCls={recuCls}"
HEADERS = {"X-HKMC-SERVICE": "HM", "X-Requested-With": "XMLHttpRequest"}
ENGINEERING_SECTORS = {"IT", "연구개발"}
PAGE_SIZE = 100


def keep(job: dict[str, Any]) -> bool:
    return job.get("secCodeNm") in ENGINEERING_SECTORS


def to_posting(job: dict[str, Any]) -> RawPosting:
    fields = [("부문", job.get("secCodeNm")), ("분야", job.get("fldCodeNm")), ("채용형태", job.get("channelCodeNm")),
              ("공고구분", job.get("jdRecuCateNm")), ("근무지", job.get("workPlaceCodeNm") or job.get("appDispWorkplace")),
              ("태그", job.get("hashTag"))]
    desc = "\n".join(f"{k}: {v}" for k, v in fields if v)
    desc += "\n(상세 JD는 지원 링크에서 확인. 목록 API만 공개되어 본문 미수집)"
    ids = {k: job[k] for k in ("recuYy", "recuType", "recuCls")}
    return RawPosting(
        company="hyundai",
        external_id="-".join(str(v) for v in ids.values()),
        title=job["recuNoticeNm"].strip(),
        apply_url=VIEW_URL.format(**ids),
        deadline=parse_date(job.get("applyEndDt"), "%Y%m%d"),
        description=desc,
        category=f"{job.get('secCodeNm')}/{job.get('fldCodeNm')}",
        raw=job,
    )


def parse_list(data: dict[str, Any]) -> list[RawPosting]:
    return [to_posting(j) for j in data["data"]["list"] if keep(j)]


class HyundaiScraper(Scraper):
    company = "hyundai"
    display_name = "현대자동차"
    careers_url = "https://talent.hyundai.com/apply/applyList.hc"
    expected_count = 28
    has_description = False

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        out: list[RawPosting] = []
        page = 1
        while True:
            r = await client.get(LIST_URL, params={"hgrCd": "1", "lang": "ko", "page": page, "pageblock": PAGE_SIZE},
                                 headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            out += parse_list(data)
            total = int(data["data"].get("listCnt") or 0)
            if page * PAGE_SIZE >= total or not data["data"]["list"]:
                break
            page += 1
        return out
