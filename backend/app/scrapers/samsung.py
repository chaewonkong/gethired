import asyncio
import re
from datetime import date
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text, parse_date

# 삼성 채용 통합 사이트. 공고(notice) 하나에 여러 직무(item)가 묶여 있어 직무 단위로 RawPosting을 만든다.
LIST_URL = "https://www.samsungcareers.com/hr/list.data"
DETAIL_URL = "https://www.samsungcareers.com/recruit/detail.data"
NOTICE_URL = "https://www.samsungcareers.com/hr/?no={seqno}"
LIST_FORM = {"intNo": "0", "strVal": "", "strTxt": "", "strKey": "", "strCompany": "", "strType": "",
             "strOrderBy": "", "strEntity": ""}
COMPANY_KEYWORD = "삼성전자"
_SEQ_RE = re.compile(r'<a[^>]*data-value="([\d,]+)"')  # 공고 링크 앵커만 (공유 버튼·카운트 제외)
_MAX_RE = re.compile(r'class="divCnt"[^>]*data-max="(\d+)"')
_DATE_RE = re.compile(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})")


def parse_list(html: str) -> tuple[list[str], int]:
    seqnos = list(dict.fromkeys(v.replace(",", "") for v in _SEQ_RE.findall(html)))
    m = _MAX_RE.search(html)
    return seqnos, int(m.group(1)) if m else 1


def _date(s: str | None) -> date | None:
    m = _DATE_RE.search(s or "")
    return parse_date("".join(m.groups()), "%Y%m%d") if m else None


def is_target(result: dict[str, Any]) -> bool:
    return COMPANY_KEYWORD in (result.get("cmpNameKr") or "") or COMPANY_KEYWORD in (result.get("title") or "")


def parse_detail(detail: dict[str, Any], seqno: str) -> list[RawPosting]:
    """seqno는 목록의 data-value(공유 링크 ?no=). result.seqno와는 다른 값이라 호출 시 넘겨받는다."""
    data = detail.get("data") or {}
    result = data.get("result")
    if not result or not is_target(result):
        return []
    out = []
    for item in data.get("items") or []:
        sections = [("담당업무", item.get("taskKr")), ("자격요건", item.get("qlfctKr")), ("우대사항", item.get("favorKr")),
                    ("근무지", item.get("workPlaceKr")), ("참고", item.get("explnKr") or item.get("memoKr"))]
        desc = "\n".join(f"[{h}]\n{html_to_text(v)}" for h, v in sections if html_to_text(v))
        out.append(RawPosting(
            company="samsung",
            external_id=f"{seqno}-{item['seq']}",
            title=f"{result['title']} — {item.get('titleKr') or ''}".strip(" —"),
            apply_url=NOTICE_URL.format(seqno=seqno),
            deadline=_date(result.get("enddate") or result.get("dtEnd")),
            description=desc or None,
            category=f"{result.get('cmpNameKr')}/{item.get('taskCode')}",
            raw={"result": result, "item": item},
        ))
    return out


class SamsungScraper(Scraper):
    company = "samsung"
    display_name = "삼성전자"
    careers_url = "https://www.samsungcareers.com/hr/"
    expected_count = 1  # 그룹 통합 공고 중 삼성전자 분만. 시기에 따라 0~수 건

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.samsungcareers.com/hr/"}
        seqnos: list[str] = []
        page, max_page = 1, 1
        while page <= max_page:
            r = await client.post(LIST_URL, data={**LIST_FORM, "currentPageNo": str(page)}, headers=headers)
            r.raise_for_status()
            found, max_page = parse_list(r.text)
            seqnos += found
            page += 1

        sem = asyncio.Semaphore(5)

        async def detail(seqno: str) -> list[RawPosting]:
            async with sem:
                r = await client.get(DETAIL_URL, params={"seqno": seqno, "strCode": ""}, headers=headers)
                r.raise_for_status()
                return parse_detail(r.json(), seqno)

        results = await asyncio.gather(*(detail(s) for s in seqnos))
        return [p for ps in results for p in ps]
