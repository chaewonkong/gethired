import asyncio
import json
import sys
from typing import Literal

from pydantic import BaseModel, Field

from .config import MATCH_BATCH_SIZE, MATCH_CONCURRENCY
from .llm import LLMResult, ask_json
from .profile import Profile
from .scrapers import RawPosting

LEVELS = ("strong", "good", "stretch")
LEVEL_MIN = {"strong": 80, "good": 65, "stretch": 45, "exclude": 0}
GAP_KINDS = ("language", "framework", "seniority", "domain", "other")
DESC_LIMIT = 2500


def level_for(score: int) -> str:
    return next(lv for lv in ("strong", "good", "stretch", "exclude") if score >= LEVEL_MIN[lv])


class Match(BaseModel):
    external_id: str
    fit_level: Literal["strong", "good", "stretch", "exclude"]
    score: int = Field(ge=0, le=100)
    gaps: list[str]
    summary: str = Field(min_length=10)
    tech_stack: list[str]
    fit_reason: str = Field(min_length=20)

    @property
    def stored(self) -> bool:
        return self.fit_level != "exclude"


class Batch(BaseModel):
    matches: list[Match]


SYSTEM = """당신은 시니어 테크 리크루터입니다. 지원자 프로필과 채용 공고 목록을 보고 각 공고의 적합도를 판정합니다.
판정 규칙:
- 먼저 하드 불일치를 봅니다. 역할 종류 자체가 다르면(비개발, 모바일/프론트엔드 전담, 보안·ML 전문직, 영업 등) fit_level=exclude, score 0~44. exclude는 저장되지 않고 버려집니다.
- 역할이 백엔드/서버/플랫폼/데이터 엔지니어링이면 exclude로 보내지 않습니다. 언어·프레임워크·연차가 다른 것은 소프트 불일치로, 등급을 한 단계 낮추되 제외하지 않습니다. 도메인(결제, 매칭, 실시간 판정, 분석 인프라 등)이 유사하면 언어가 달라도 good까지 줄 수 있습니다.
- fit_level과 score 구간: strong 80~100 (주력 스택·도메인·연차 모두 맞음), good 65~79 (핵심은 맞고 한 요소가 약함), stretch 45~64 (역할·도메인은 맞지만 언어/프레임워크나 연차가 다름, 지원 가능하나 서류 리스크), exclude 0~44 (역할 자체가 다름). fit_level은 반드시 score 구간과 일치해야 합니다.
- score 배점: 주력 스택 일치(35), 도메인/업무 성격 일치(35), 연차·시니어리티 일치(20), 우대사항 일치(10).
- gaps: 부족한 점을 "종류: 설명" 형식으로. 종류는 language, framework, seniority, domain, other 중 하나. 예: "language: Kotlin/Spring 필수, 지원자는 Go 주력". 없으면 빈 리스트.
- summary: 공고가 요구하는 역할을 한국어 1~2문장으로.
- tech_stack: 공고에 명시된 기술만. 추측 금지. 없으면 빈 리스트.
- fit_reason: 왜 맞는지/안 맞는지를 지원자 프로필의 구체 경험(프로젝트, 기술, 성과)을 인용해 한국어 2~3문장으로. 일반론 금지. exclude는 1문장으로 짧게.
- 입력된 모든 공고에 대해 정확히 하나씩, external_id를 그대로 써서 응답합니다. 누락·추가 금지."""


def render(p: RawPosting) -> str:
    desc = (p.description or "")[:DESC_LIMIT]
    return (f'<posting external_id="{p.external_id}">\n회사: {p.company}\n제목: {p.title}\n'
            f"분류: {p.category}\n마감: {p.deadline or '미정'}\n본문:\n{desc}\n</posting>")


async def judge_batch(profile: Profile, batch: list[RawPosting], sem: asyncio.Semaphore,
                      retries: int = 2) -> tuple[list[Match], list[LLMResult]]:
    ids = {p.external_id for p in batch}
    results: list[LLMResult] = []
    got: dict[str, Match] = {}
    pending = batch
    for _ in range(retries + 1):
        prompt = (f"<profile>\n{json.dumps(profile.model_dump(), ensure_ascii=False)}\n</profile>\n\n"
                  f'<postings count="{len(pending)}">\n' + "\n".join(render(p) for p in pending) + "\n</postings>")
        async with sem:
            res = await ask_json(prompt, Batch.model_json_schema(), system_prompt=SYSTEM)
        results.append(res)
        for m in Batch.model_validate(res.data).matches:
            if m.external_id in ids:
                if m.fit_level != level_for(m.score):
                    m.fit_level = level_for(m.score)  # score 구간이 기준
                got[m.external_id] = m
        pending = [p for p in pending if p.external_id not in got]
        if not pending:
            break
        print(f"matcher: retrying {len(pending)} missing ids", file=sys.stderr)
    return [got[p.external_id] for p in batch if p.external_id in got], results


async def judge(profile: Profile, postings: list[RawPosting], batch_size: int = MATCH_BATCH_SIZE,
                concurrency: int = MATCH_CONCURRENCY) -> tuple[list[Match], list[LLMResult]]:
    if not postings:
        return [], []
    batches = [postings[i:i + batch_size] for i in range(0, len(postings), batch_size)]
    sem = asyncio.Semaphore(concurrency)
    outs = await asyncio.gather(*(judge_batch(profile, b, sem) for b in batches))
    return [m for ms, _ in outs for m in ms], [r for _, rs in outs for r in rs]


def to_row(p: RawPosting, m: Match, now: str) -> dict:
    return {
        "company": p.company, "external_id": p.external_id, "title": p.title, "summary": m.summary,
        "tech_stack": m.tech_stack, "fit_level": m.fit_level, "score": m.score, "gaps": m.gaps,
        "fit_reason": m.fit_reason, "apply_url": p.apply_url,
        "deadline": p.deadline.isoformat() if p.deadline else None, "category": p.category, "scraped_at": now,
    }
