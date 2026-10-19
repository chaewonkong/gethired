"""컬리 (GreetingHR) 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
from pathlib import Path

from app.scrapers import greetinghr
from app.scrapers.kurly import KurlyScraper

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def test_kurly_keep_filters_by_occupation():
    openings = load("kurly_openings.json")
    kept = [o for o in openings if KurlyScraper().keep(o)]
    assert kept and len(kept) < len(openings)
    assert all(greetinghr.occupations(o) & KurlyScraper.keep_occupations for o in kept)


def test_kurly_to_posting():
    opening = next(o for o in load("kurly_openings.json") if o["openingId"] == 170984)
    p = KurlyScraper().to_posting(opening, load("kurly_detail.json"))
    assert p.company == "kurly"
    assert p.external_id == "170984"
    assert p.apply_url == "https://kurly.career.greetinghr.com/ko/o/170984"
    assert p.category == "개발"
    assert p.deadline is None
    assert "<" not in p.description and len(p.description) > 300
