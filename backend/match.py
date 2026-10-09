import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from llm import ClaudeAuthError, LLMResult, ask_json
from profile import Profile, get_profile

OUT_DIR = Path(__file__).parent / "out"
DESC_LIMIT = 1500

PLANTED = [
    {"company": "planted", "external_id": "planted-fit", "title": "Backend Engineer, Matchmaking (Go)",
     "apply_url": "https://example.com/fit", "deadline": None, "category": "Tech",
     "description": "실시간 게임 매치메이킹 플랫폼의 백엔드 엔지니어를 찾습니다. Go, Redis, Kubernetes 기반 매치메이커 운영 및 차기 버전 설계. "
                    "대규모 트래픽 분산 시스템 경험, ClickHouse/PostgreSQL 기반 지표 분석 경험 우대. 5년 이상 백엔드 경력."},
    {"company": "planted", "external_id": "planted-unfit-ios", "title": "iOS Engineer (Swift)",
     "apply_url": "https://example.com/ios", "deadline": None, "category": "Tech",
     "description": "iOS 앱 개발자를 모집합니다. Swift, SwiftUI, UIKit 3년 이상. 앱스토어 출시 경험 필수. 서버 개발 경험 불필요."},
    {"company": "planted", "external_id": "planted-unfit-sales", "title": "영업 관리자 (B2B 세일즈)",
     "apply_url": "https://example.com/sales", "deadline": None, "category": "Business",
     "description": "B2B 영업 조직을 이끌 영업 관리자를 모집합니다. 영업 파이프라인 관리, 대형 고객사 계약 협상, 영업팀 KPI 관리 5년 이상."},
]


LEVELS = ("strong", "good", "stretch")
LEVEL_MIN = {"strong": 80, "good": 65, "stretch": 45, "exclude": 0}
GAP_KINDS = ("language", "framework", "seniority", "domain", "other")


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
    def fit(self) -> bool:
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


def load_postings(companies: list[str] | None) -> list[dict]:
    from scrapers import REGISTRY

    out = []
    for name in sorted(REGISTRY):
        f = OUT_DIR / f"{name}.json"
        if (companies and name not in companies) or not f.exists():
            continue
        out += json.loads(f.read_text())
    return out


def render(p: dict) -> str:
    desc = (p.get("description") or "")[:DESC_LIMIT]
    return (f"<posting external_id=\"{p['external_id']}\">\n회사: {p['company']}\n제목: {p['title']}\n"
            f"분류: {p.get('category')}\n마감: {p.get('deadline') or '미정'}\n본문:\n{desc}\n</posting>")


async def judge_batch(profile: Profile, batch: list[dict], sem: asyncio.Semaphore, retries: int = 2) -> tuple[list[Match], list[LLMResult]]:
    ids = {p["external_id"] for p in batch}
    results: list[LLMResult] = []
    pending = batch
    got: dict[str, Match] = {}
    for attempt in range(retries + 1):
        prompt = (f"<profile>\n{json.dumps(profile.model_dump(), ensure_ascii=False)}\n</profile>\n\n"
                  f"<postings count=\"{len(pending)}\">\n" + "\n".join(render(p) for p in pending) + "\n</postings>")
        async with sem:
            res = await ask_json(prompt, Batch.model_json_schema(), system_prompt=SYSTEM)
        results.append(res)
        for m in Batch.model_validate(res.data).matches:
            if m.external_id in ids:
                if m.fit_level != level_for(m.score):
                    print(f"  level/score mismatch {m.external_id}: {m.fit_level}/{m.score} -> {level_for(m.score)}", file=sys.stderr)
                    m.fit_level = level_for(m.score)
                got[m.external_id] = m
        pending = [p for p in pending if p["external_id"] not in got]
        if not pending:
            break
        print(f"  retry {attempt + 1}: {len(pending)} missing ids", file=sys.stderr)
    return [got[p["external_id"]] for p in batch if p["external_id"] in got], results


async def run(postings: list[dict], profile: Profile, batch_size: int, concurrency: int) -> tuple[list[Match], list[LLMResult], float]:
    batches = [postings[i:i + batch_size] for i in range(0, len(postings), batch_size)]
    sem = asyncio.Semaphore(concurrency)
    started = time.monotonic()
    outs = await asyncio.gather(*(judge_batch(profile, b, sem) for b in batches))
    matches = [m for ms, _ in outs for m in ms]
    results = [r for _, rs in outs for r in rs]
    return matches, results, time.monotonic() - started


def write_fit_md(matches: list[Match], by_id: dict[str, dict], path: Path) -> None:
    lines = []
    for level in ("strong", "good", "stretch"):
        lines.append(f"# {level} ({LEVEL_MIN[level]}+)\n")
        for m in sorted((m for m in matches if m.fit_level == level), key=lambda m: -m.score):
            p = by_id[m.external_id]
            lines += [f"## [{m.score}] {p['company']} — {p['title']}", f"- 링크: {p['apply_url']}",
                      f"- 요약: {m.summary}", f"- 스택: {', '.join(m.tech_stack) or '-'}",
                      f"- 부족: {'; '.join(m.gaps) or '-'}", f"- 이유: {m.fit_reason}", ""]
    path.write_text("\n".join(lines))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("companies", nargs="*")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (디버그)")
    ap.add_argument("--planted", action="store_true", help="플랜티드 테스트 공고 3건 혼입")
    ap.add_argument("--out", default="matches.json")
    ap.add_argument("--skip-judged", action="store_true", help="--out 파일에 이미 있는 external_id는 재판정하지 않음 (증분 실행)")
    args = ap.parse_args()

    postings = load_postings(args.companies or None)
    if args.limit:
        postings = postings[: args.limit]
    if args.planted:
        postings = postings + PLANTED
        random.Random(42).shuffle(postings)
    by_id = {p["external_id"]: p for p in postings}

    # 이전 결과: 저장된 매치 + exclude된 id 목록 (judgments 테이블 역할)
    previous: list[Match] = []
    excluded_ids: set[str] = set()
    if args.skip_judged and (OUT_DIR / args.out).exists():
        prev = json.loads((OUT_DIR / args.out).read_text())
        previous = [Match.model_validate(m) for m in prev["matches"] if m["external_id"] in by_id]
        excluded_ids = {i for i in prev.get("excluded_ids", []) if i in by_id}
        judged = {m.external_id for m in previous} | excluded_ids
        todo = [p for p in postings if p["external_id"] not in judged]
        print(f"skip-judged: {len(judged)} already judged ({len(excluded_ids)} excluded), {len(todo)} new")
    else:
        todo = postings

    try:
        profile = await get_profile()
        judged_now, results, elapsed = await run(todo, profile, args.batch_size, args.concurrency) if todo else ([], [], 0.0)
    except ClaudeAuthError as e:
        print(f"auth error: {e}", file=sys.stderr)
        return 2
    missing = {p["external_id"] for p in todo} - {m.external_id for m in judged_now}
    excluded_ids |= {m.external_id for m in judged_now if m.fit_level == "exclude"}
    matches = previous + [m for m in judged_now if m.fit_level != "exclude"]

    cost = sum(r.cost_usd for r in results)
    (OUT_DIR / args.out).write_text(json.dumps(
        {"batch_size": args.batch_size, "concurrency": args.concurrency, "elapsed_s": round(elapsed, 1),
         "llm_calls": len(results), "cost_usd": round(cost, 4),
         "input_tokens": sum(r.input_tokens for r in results), "output_tokens": sum(r.output_tokens for r in results),
         "excluded_ids": sorted(excluded_ids),
         "matches": [m.model_dump() for m in matches]}, ensure_ascii=False, indent=1))
    write_fit_md(matches, by_id, OUT_DIR / "fit.md")

    by_level = {lv: sum(1 for m in matches if m.fit_level == lv) for lv in LEVELS}
    print(f"postings={len(postings)} stored={len(matches)} excluded={len(excluded_ids)} missing={len(missing)} levels={by_level}")
    print(f"batches={math.ceil(len(todo) / args.batch_size)} llm_calls={len(results)} elapsed={elapsed:.1f}s cost=${cost:.3f}")
    if args.planted:
        for pid, expect in (("planted-fit", True), ("planted-unfit-ios", False), ("planted-unfit-sales", False)):
            m = next((m for m in matches if m.external_id == pid), None)
            stored = m is not None
            ok = stored == expect and (not expect or pid not in excluded_ids)
            print(f"planted {pid}: {'OK' if ok else 'FAIL'} (stored={stored}, level={m.fit_level if m else 'exclude'})")
    companies = sorted({p["company"] for p in postings})
    for lv in ("strong", "good", "stretch"):
        print(f"{lv:7} by company: { {c: sum(1 for m in matches if m.fit_level == lv and by_id[m.external_id]['company'] == c) for c in companies} }")
    bad_gaps = [g for m in matches for g in m.gaps if g.split(":")[0].strip() not in GAP_KINDS]
    if bad_gaps:
        print(f"gaps with unknown kind: {bad_gaps[:5]}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
