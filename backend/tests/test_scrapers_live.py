"""실제 채용 사이트를 호출하는 통합 테스트. 기본 스킵, `LIVE=1 uv run pytest tests/test_scrapers_live.py`로 실행."""
import asyncio
import os
from collections import Counter

import pytest

from app.scrapers import REGISTRY, make_client

pytestmark = pytest.mark.skipif(not os.environ.get("LIVE"), reason="set LIVE=1 to hit real career sites")


@pytest.mark.parametrize("company", sorted(REGISTRY))
def test_scraper_returns_valid_postings(company):
    async def run():
        async with make_client() as client:
            return await REGISTRY[company]().fetch(client)

    postings = asyncio.run(run())
    assert postings, f"{company}: 0 postings"
    assert all(p.external_id and p.title and p.apply_url.startswith("http") for p in postings)
    assert max(Counter(p.external_id for p in postings).values()) == 1, "duplicate external_id"
    if REGISTRY[company].has_description:
        with_desc = sum(1 for p in postings if p.description and len(p.description) >= 100)
        assert with_desc / len(postings) >= 0.9, f"{company}: description coverage {with_desc}/{len(postings)}"
    expected = REGISTRY[company].expected_count
    assert expected * 0.5 <= len(postings) <= expected * 2, f"{company}: {len(postings)} vs expected {expected}"
