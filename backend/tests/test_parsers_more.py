"""spec 0006 회사들의 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
from datetime import date
from pathlib import Path

import pytest

from app.scrapers import REGISTRY, fortytwodot, greetinghr, hyperconnect, kakaobank, woowahan
from app.scrapers.kakaopay import KakaoPayScraper
from app.scrapers.upstage import UpstageScraper

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def next_data_html(props: dict) -> str:
    payload = json.dumps({"props": {"pageProps": props}}, ensure_ascii=False)
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{payload}</script></body></html>'


def dehydrated(*queries: tuple[list, object]) -> dict:
    return {"dehydratedState": {"queries": [{"queryKey": k, "state": {"data": d}} for k, d in queries]}}


# --- GreetingHR (upstage, kakaopay) ---

def test_greetinghr_parses_next_data_queries():
    openings = load("upstage_openings.json")
    info = load("upstage_detail.json")
    assert greetinghr.parse_openings(next_data_html(dehydrated((["openings"], openings)))) == openings
    html = next_data_html(dehydrated(
        (["publicCareer", "getCareerBaseInfo", "careers"], {}),
        (["career", "getOpeningById", {"openingId": 1}], {"data": {"openingsInfo": info}}),
    ))
    assert greetinghr.parse_opening_info(html) == info
    with pytest.raises(ValueError):
        greetinghr.page_props("<html></html>")
    with pytest.raises(KeyError):
        greetinghr.parse_openings(next_data_html(dehydrated()))


@pytest.mark.parametrize("cls, name, occupation", [(UpstageScraper, "upstage", "Tech"), (KakaoPayScraper, "kakaopay", "기술")])
def test_greetinghr_keep_filters_by_occupation(cls, name, occupation):
    openings = load(f"{name}_openings.json")
    kept = [o for o in openings if cls().keep(o)]
    assert kept and len(kept) < len(openings)
    assert all(occupation in greetinghr.occupations(o) for o in kept)


def test_greetinghr_keep_handles_missing_positions():
    opening = dict(load("upstage_openings.json")[0])
    opening["openingJobPosition"] = None
    assert greetinghr.occupations(opening) == set()
    assert not UpstageScraper().keep(opening)
    opening["openingJobPosition"] = {"openingJobPositions": [{"workspaceOccupation": None}]}
    assert greetinghr.occupations(opening) == {"?"}


def test_upstage_to_posting():
    opening = load("upstage_openings.json")[0]
    info = load("upstage_detail.json")
    p = UpstageScraper().to_posting(opening, info)
    assert p.company == "upstage" and p.external_id == "217109"
    assert p.apply_url == "https://careers.upstage.ai/ko/o/217109"
    assert p.category == "Tech"
    assert p.deadline is None
    assert p.description and "<" not in p.description and len(p.description) > 500


def test_kakaopay_to_posting_with_due_date():
    opening = load("kakaopay_openings.json")[0]
    info = dict(load("kakaopay_detail.json"), dueDate="2026-12-31T14:59:59Z")
    p = KakaoPayScraper().to_posting(opening, info)
    assert p.company == "kakaopay" and p.apply_url == "https://careers.kakaopay.com/ko/o/216356"
    assert p.deadline == date(2026, 12, 31)
    assert p.category == "기술"
    assert "조직 소개" in p.description


def test_greetinghr_base_is_not_registered():
    assert "upstage" in REGISTRY and "kakaopay" in REGISTRY
    assert all(not issubclass(c, greetinghr.GreetingHRScraper) or c.company in ("upstage", "kakaopay") for c in REGISTRY.values())


# --- hyperconnect (Lever), 42dot (Ashby) ---

def test_hyperconnect_keeps_seoul_including_match_group():
    jobs = load("hyperconnect_lever.json")
    postings = hyperconnect.parse(jobs)
    assert postings and len(postings) < len(jobs)
    assert all(p.company == "hyperconnect" and p.apply_url.startswith("https://jobs.lever.co/") for p in postings)
    assert any(p.category.startswith("Match Group/") for p in postings)
    assert any(p.category.startswith("Hyperconnect/") for p in postings)
    assert not any("Seoul" not in j["categories"]["location"] for j in jobs if hyperconnect.keep(j))


def test_hyperconnect_description_joins_lists():
    job = load("hyperconnect_lever.json")[0]
    desc = hyperconnect.description(job)
    assert job["descriptionPlain"].strip()[:40] in desc
    assert all(lst["text"] in desc for lst in job["lists"])
    assert "<li>" not in desc


def test_fortytwodot_keeps_korea_engineering():
    data = load("fortytwodot_ashby.json")
    postings = fortytwodot.parse(data)
    assert postings and len(postings) < len(data["jobs"])
    assert all(p.company == "42dot" and p.category.startswith("ENGINEERING/") for p in postings)
    assert all(p.apply_url.startswith("https://jobs.ashbyhq.com/42dot/") for p in postings)
    assert all(p.description for p in postings)
    unlisted = dict(data["jobs"][0], isListed=False)
    assert not fortytwodot.keep(unlisted)


# --- woowahan, kakaobank ---

def test_woowahan_to_posting_and_open_ended_deadline():
    jobs = load("woowahan_list.json")["data"]["list"]
    detail = load("woowahan_detail.json")["data"]
    p = woowahan.to_posting(jobs[0], detail)
    assert p.company == "woowahan" and p.external_id == jobs[0]["recruitNumber"]
    assert p.apply_url == f"https://career.woowahan.com/recruitment/{p.external_id}/detail"
    assert p.category == woowahan.DEV_JOB_GROUP
    assert p.description and "<" not in p.description and len(p.description) > 200
    assert woowahan.deadline("9999-12-31 00:00:00") is None
    assert woowahan.deadline("2999-12-31 00:00:00") is None
    assert woowahan.deadline("2026-11-30 23:59:59") == date(2026, 11, 30)
    assert woowahan.deadline(None) is None


def test_kakaobank_keep_and_to_posting():
    data = load("kakaobank_list.json")
    kept = [j for j in data["list"] if kakaobank.keep(j)]
    assert kept and len(kept) < len(data["list"])
    assert all(j["recruitClassName"] in kakaobank.TECH_CLASSES for j in kept)
    detail = load("kakaobank_detail.json")
    p = kakaobank.to_posting(kept[0], detail)
    assert p.company == "kakaobank" and p.external_id == str(kept[0]["recruitNoticeSn"])
    assert p.apply_url == f"https://recruit.kakaobank.com/jobs/{p.external_id}"
    assert p.deadline == date.fromisoformat(kept[0]["receiveEndDatetime"][:10])
    assert p.category == kept[0]["recruitClassName"]
    assert p.description and "<" not in p.description and len(p.description) > 200
