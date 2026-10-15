import json
import re
from typing import Any

import httpx

from .base import RawPosting, Scraper, html_to_text

# 두나무 채용 사이트는 Next.js App Router. 공개 API가 없어 `RSC: 1` 헤더로 받은 서버 컴포넌트 페이로드에서
# react-query dehydrated 데이터를 꺼낸다. 본문은 `"$<id>"` 참조이고, 실제 HTML은 같은 페이로드의 `<id>:T<hex 길이>,` 청크에 있다.
# 길이는 UTF-8 바이트 수이고 청크 뒤에는 개행 없이 다음 행이 바로 이어지므로 바이트로 순차 파싱한다.
# 상세 페이지에는 같은 공고의 content 항목이 둘 있는데(전역 캐시 + 페이지 쿼리) 참조가 해결되는 쪽만 청크를 가진다.
BASE = "https://careers.dunamu.com"
HEADERS = {"RSC": "1"}
TECH_GROUPS = {"T_ENGINEERING", "T_SECURITY", "T_DATA"}
_LIST_RE = re.compile(rb'"jobNoticeResponses":(\[.*?\])\s*[,}]', re.S)
_CONTENT_RE = re.compile(rb'"content":(\{"jobNoticeId".*?\}),"statusCode"')
_CHUNK_RE = re.compile(rb"([0-9a-f]+):T([0-9a-f]+),")


def text_chunks(rsc: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    pos = 0
    while (m := _CHUNK_RE.search(rsc, pos)) is not None:
        end = m.end() + int(m.group(2), 16)
        out[m.group(1).decode()] = rsc[m.end():end].decode("utf-8", "replace")
        pos = end
    return out


def parse_list(rsc: bytes) -> list[dict[str, Any]]:
    m = _LIST_RE.search(rsc)
    if not m:
        raise ValueError("jobNoticeResponses not found")
    return json.loads(m.group(1))


def parse_detail(rsc: bytes, position_id: int) -> dict[str, Any]:
    chunks = text_chunks(rsc)
    fallback = None
    for m in _CONTENT_RE.finditer(rsc):
        c = json.loads(m.group(1))
        if c.get("positionId") != position_id:
            continue
        body = c.get("jobNoticeContent") or ""
        if body.startswith("$"):
            body = chunks.get(body[1:])
            if body is None:
                fallback = fallback or c
                continue
        return dict(c, jobNoticeContent=body)
    if fallback is None:
        raise KeyError(position_id)
    return dict(fallback, jobNoticeContent="")


def keep(job: dict[str, Any]) -> bool:
    return job.get("jobGroupCode") in TECH_GROUPS


def to_posting(job: dict[str, Any], detail: dict[str, Any]) -> RawPosting:
    return RawPosting(
        company="dunamu",
        external_id=str(job["id"]),
        title=job["name"].strip(),
        apply_url=f"{BASE}/detail/{job['id']}",
        description=html_to_text(detail.get("jobNoticeContent")),
        category=f"{job.get('jobGroupCode')}/{job.get('experienceLevel')}",
        raw=detail,
    )


class DunamuScraper(Scraper):
    company = "dunamu"
    display_name = "두나무"
    careers_url = "https://careers.dunamu.com"
    expected_count = 5

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        r = await client.get(f"{BASE}/", headers=HEADERS)
        r.raise_for_status()
        out: list[RawPosting] = []
        for job in parse_list(r.content):
            if not keep(job):
                continue
            d = await client.get(f"{BASE}/detail/{job['id']}", headers=HEADERS)
            d.raise_for_status()
            out.append(to_posting(job, parse_detail(d.content, job["id"])))
        return out
