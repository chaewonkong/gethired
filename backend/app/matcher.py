import asyncio
import json
import sys
from typing import Literal

from pydantic import BaseModel, Field

from .config import MATCH_BATCH_SIZE, MATCH_CONCURRENCY
from .llm import LLMResult, ask_json
from .profile import ROLES, Profile
from .scrapers import RawPosting

LEVELS = ("strong", "good", "stretch")
LEVEL_MIN = {"strong": 80, "good": 65, "stretch": 45, "exclude": 0}
GAP_KINDS = ("role", "language", "framework", "seniority", "domain", "other")
DESC_LIMIT = 2500

# 인접 직군: 서로 대체 지원이 현실적인 쌍만. exclude 금지, stretch 이상. 대칭 (test_matcher가 고정)
ADJACENT: dict[str, tuple[str, ...]] = {
    "backend": ("fullstack", "data-engineering", "infra-sre"),
    "frontend": ("fullstack", "cross-platform-mobile"),
    "fullstack": ("backend", "frontend"),
    "ios": ("android", "cross-platform-mobile"),
    "android": ("ios", "cross-platform-mobile", "embedded"),
    "cross-platform-mobile": ("ios", "android", "frontend"),
    "data-engineering": ("backend", "ml-engineering", "data-science"),
    "data-science": ("data-engineering", "ml-engineering"),
    "ml-engineering": ("data-engineering", "data-science", "ml-research"),
    "ml-research": ("ml-engineering",),
    "infra-sre": ("backend", "security-engineering"),
    "security-engineering": ("infra-sre",),
    "qa": (),
    "embedded": ("android", "game-client"),
    "game-client": ("embedded",),
}


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


def render_adjacent() -> str:
    return "\n".join(f"  - {role}: {', '.join(adj) or '(없음)'}" for role, adj in ADJACENT.items())


SYSTEM = f"""당신은 시니어 테크 리크루터입니다. 지원자 프로필과 채용 공고 목록을 보고 각 공고의 적합도를 판정합니다. 지원자는 어떤 소프트웨어 엔지니어링 직군이든 될 수 있습니다. 판정의 역할 기준은 프로필의 roles이며, 특정 직군을 가정하지 않습니다.

직군 어휘: {", ".join(ROLES)}

판정 순서:
1. 공고의 직군을 위 어휘로 식별합니다.
2. 하드 불일치 → fit_level=exclude, score 0~44. exclude는 저장되지 않고 버려집니다.
   - 소프트웨어 엔지니어링이 아닌 직군: 디자인, PM/PO/기획, 영업, 마케팅, HR, 재무·회계, CS, 법무, 정책·감사·개인정보 관리직(Privacy/Security Policy/IT Audit Manager 등), TPM·DevRel·테크니컬 라이터, 데이터 분석가.
     예외: 데이터 분석가는 지원자 roles에 data-science 또는 data-engineering이 있으면 stretch까지 줄 수 있습니다.
   - 소프트웨어 엔지니어링이지만 지원자 roles와 같지도 인접하지도 않고, 공고의 필수 기술이 지원자 core_skills와도 겹치지 않는 직군 (예: 지원자 frontend ↔ 공고 ml-research).
3. 같은 직군이거나 인접 직군이면 exclude하지 않습니다. 인접 직군은 stretch 이상입니다. 인접 표(대칭):
{render_adjacent()}
   - 지원자 roles가 비어 있으면 core_skills·domains·summary로 직군을 추정해 같은 규칙을 적용합니다.
   - 인접이 아니어도 공고의 필수 기술이 core_skills와 겹치면 exclude하지 않습니다.
4. 소프트 불일치: 같은 직군 안에서 언어·프레임워크·연차가 다른 것. 등급을 한 단계 낮추되 제외하지 않습니다. 도메인(결제, 매칭, 실시간 판정, 분석 인프라 등)이 유사하면 언어가 달라도 good까지 줄 수 있습니다.

등급과 score 구간: strong 80~100 (핵심 기술·도메인·연차 모두 맞음), good 65~79 (핵심은 맞고 한 요소가 약함), stretch 45~64 (직군·도메인은 맞지만 언어/프레임워크나 연차가 다름, 또는 인접 직군. 지원 가능하나 서류 리스크), exclude 0~44 (하드 불일치). fit_level은 반드시 score 구간과 일치해야 합니다.
score 배점: 핵심 기술 일치(35), 도메인/업무 성격 일치(35), 연차·시니어리티 일치(20), 우대사항 일치(10). 핵심 기술은 직군에 따라 언어·프레임워크·플랫폼·도구를 모두 포함합니다. preferences.target_roles·target_domains와 맞는 공고는 우대사항 10점 안에서 가점하고, exclude 판단에는 쓰지 않습니다.

출력 규칙:
- gaps: 부족한 점을 "종류: 설명" 형식으로. 종류는 {", ".join(GAP_KINDS)} 중 하나. 예: "role: iOS 전담, 지원자는 웹 프론트엔드", "language: Kotlin/Spring 필수, 지원자는 Go 주력". 없으면 빈 리스트.
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
