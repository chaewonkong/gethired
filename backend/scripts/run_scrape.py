"""스크래퍼 단독 실행 (디버그용). DB를 건드리지 않고 out/<company>.json에 저장."""
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from app.scrapers import REGISTRY, RawPosting, Scraper, make_client  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out"


async def run_one(scraper: Scraper) -> tuple[str, list[RawPosting] | None, str | None, float]:
    started = time.monotonic()
    try:
        async with make_client() as client:
            postings = await scraper.fetch(client)
        if not postings:
            raise RuntimeError("0 postings (schema change?)")
        return scraper.company, postings, None, time.monotonic() - started
    except (Exception, ValidationError) as e:  # noqa: BLE001
        return scraper.company, None, f"{type(e).__name__}: {str(e)[:120]}", time.monotonic() - started


def check(company: str, postings: list[RawPosting]) -> list[str]:
    warnings = []
    expected = REGISTRY[company].expected_count
    if not expected * 0.7 <= len(postings) <= expected * 1.3:
        warnings.append(f"count {len(postings)} outside ±30% of expected {expected}")
    dup = [k for k, n in Counter(p.external_id for p in postings).items() if n > 1]
    if dup:
        warnings.append(f"duplicate external_id: {dup[:5]}")
    with_desc = sum(1 for p in postings if p.description and len(p.description) >= 100)
    if REGISTRY[company].has_description and with_desc / len(postings) < 0.95:
        warnings.append(f"description coverage {with_desc}/{len(postings)}")
    return warnings


async def main() -> int:
    OUT.mkdir(exist_ok=True)
    only = sys.argv[1:]
    scrapers = [cls() for name, cls in REGISTRY.items() if not only or name in only]
    t0 = time.monotonic()
    results = await asyncio.gather(*(run_one(s) for s in scrapers))
    total_elapsed = time.monotonic() - t0

    failed = 0
    print(f"{'company':8} {'status':7} {'count':>5} {'sec':>5}  note")
    for company, postings, error, elapsed in results:
        if postings is None:
            failed += 1
            print(f"{company:8} {'failed':7} {'-':>5} {elapsed:5.1f}  {error}")
            continue
        (OUT / f"{company}.json").write_text(
            json.dumps([p.model_dump(mode="json") for p in postings], ensure_ascii=False, indent=1))
        print(f"{company:8} {'ok':7} {len(postings):>5} {elapsed:5.1f}  {'; '.join(check(company, postings))}")
        print(f"{'':8} categories: {dict(Counter(p.category for p in postings).most_common(8))}")

    total = sum(len(ps) for _, ps, _, _ in results if ps)
    print(f"\ntotal {total} postings, {failed} failed, {total_elapsed:.1f}s wall")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
