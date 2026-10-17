"""매칭 단독 실행 (디버그/품질 검토용). out/<company>.json을 읽어 out/matches.json, out/fit.md 생성. DB 미사용."""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm  # noqa: E402
from app.config import DB_PATH, LLM_PROVIDER  # noqa: E402
from app.llm import LLMAuthError  # noqa: E402
from app.matcher import LEVEL_MIN, LEVELS, Match, judge  # noqa: E402
from app.profile import get_profile  # noqa: E402
from app.repository import Repository  # noqa: E402
from app.scrapers import REGISTRY, RawPosting  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "out"

PLANTED = [
    RawPosting(company="planted", external_id="planted-fit", title="Backend Engineer, Matchmaking (Go)",
               apply_url="https://example.com/fit", category="Tech",
               description="실시간 게임 매치메이킹 플랫폼의 백엔드 엔지니어를 찾습니다. Go, Redis, Kubernetes 기반 매치메이커 운영 및 차기 버전 설계. "
                           "대규모 트래픽 분산 시스템 경험, ClickHouse/PostgreSQL 기반 지표 분석 경험 우대. 5년 이상 백엔드 경력."),
    RawPosting(company="planted", external_id="planted-unfit-ios", title="iOS Engineer (Swift)",
               apply_url="https://example.com/ios", category="Tech",
               description="iOS 앱 개발자를 모집합니다. Swift, SwiftUI, UIKit 3년 이상. 앱스토어 출시 경험 필수. 서버 개발 경험 불필요."),
    RawPosting(company="planted", external_id="planted-unfit-sales", title="영업 관리자 (B2B 세일즈)",
               apply_url="https://example.com/sales", category="Business",
               description="B2B 영업 조직을 이끌 영업 관리자를 모집합니다. 영업 파이프라인 관리, 대형 고객사 계약 협상, 영업팀 KPI 관리 5년 이상."),
]


def load_postings(companies: list[str] | None) -> list[RawPosting]:
    out: list[RawPosting] = []
    for name in sorted(REGISTRY):
        f = OUT_DIR / f"{name}.json"
        if (companies and name not in companies) or not f.exists():
            continue
        out += [RawPosting.model_validate(p) for p in json.loads(f.read_text())]
    return out


def write_fit_md(matches: list[Match], by_id: dict[str, RawPosting], path: Path) -> None:
    lines = []
    for level in LEVELS:
        lines.append(f"# {level} ({LEVEL_MIN[level]}+)\n")
        for m in sorted((m for m in matches if m.fit_level == level), key=lambda m: -m.score):
            p = by_id[m.external_id]
            lines += [f"## [{m.score}] {p.company} — {p.title}", f"- 링크: {p.apply_url}",
                      f"- 요약: {m.summary}", f"- 스택: {', '.join(m.tech_stack) or '-'}",
                      f"- 부족: {'; '.join(m.gaps) or '-'}", f"- 이유: {m.fit_reason}", ""]
    path.write_text("\n".join(lines))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("companies", nargs="*")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--planted", action="store_true")
    ap.add_argument("--out", default="matches.json")
    ap.add_argument("--skip-judged", action="store_true")
    ap.add_argument("--provider", choices=llm.PROVIDERS, default=None, help=f"기본 $LLM_PROVIDER ({LLM_PROVIDER})")
    args = ap.parse_args()
    llm.configure(args.provider or LLM_PROVIDER)

    postings = load_postings(args.companies or None)
    if args.limit:
        postings = postings[: args.limit]
    if args.planted:
        postings = postings + PLANTED
        random.Random(42).shuffle(postings)
    by_id = {p.external_id: p for p in postings}

    previous: list[Match] = []
    excluded_ids: set[str] = set()
    out_path = OUT_DIR / args.out
    if args.skip_judged and out_path.exists():
        prev = json.loads(out_path.read_text())
        previous = [Match.model_validate(m) for m in prev["matches"] if m["external_id"] in by_id]
        excluded_ids = {i for i in prev.get("excluded_ids", []) if i in by_id}
    judged = {m.external_id for m in previous} | excluded_ids
    todo = [p for p in postings if p.external_id not in judged]

    try:
        profile = await get_profile(Repository(DB_PATH))
        judged_now, results = await judge(profile, todo, args.batch_size, args.concurrency)
    except LLMAuthError as e:
        print(f"auth error: {e}", file=sys.stderr)
        return 2
    missing = {p.external_id for p in todo} - {m.external_id for m in judged_now}
    excluded_ids |= {m.external_id for m in judged_now if not m.stored}
    matches = previous + [m for m in judged_now if m.stored]
    cost = sum(r.cost_usd for r in results)

    out_path.write_text(json.dumps(
        {"llm_calls": len(results), "cost_usd": round(cost, 4), "excluded_ids": sorted(excluded_ids),
         "matches": [m.model_dump() for m in matches]}, ensure_ascii=False, indent=1))
    write_fit_md(matches, by_id, OUT_DIR / "fit.md")

    by_level = {lv: sum(1 for m in matches if m.fit_level == lv) for lv in LEVELS}
    print(f"postings={len(postings)} stored={len(matches)} excluded={len(excluded_ids)} missing={len(missing)} levels={by_level}")
    print(f"provider={llm.current_provider()} llm_calls={len(results)} cost=${cost:.3f}")
    if args.planted:
        for pid, expect in (("planted-fit", True), ("planted-unfit-ios", False), ("planted-unfit-sales", False)):
            stored = any(m.external_id == pid for m in matches)
            print(f"planted {pid}: {'OK' if stored == expect else 'FAIL'}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
