"""spec 0006 회사들의 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
import re
from datetime import date
from pathlib import Path

import pytest

from app.scrapers import REGISTRY, dunamu, fortytwodot, greetinghr, hyperconnect, kakaobank, nhn, woowahan
from app.scrapers.kakaomobility import KakaoMobilityScraper
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


# --- GreetingHR (upstage, kakaopay, kakaomobility) ---

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


@pytest.mark.parametrize("cls, name, occupation", [
    (UpstageScraper, "upstage", "Tech"),
    (KakaoPayScraper, "kakaopay", "기술"),
    (KakaoMobilityScraper, "kakaomobility", "기술"),
])
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


def test_kakaomobility_to_posting_without_due_date():
    opening = next(o for o in load("kakaomobility_openings.json") if o["openingId"] == 236686)
    p = KakaoMobilityScraper().to_posting(opening, load("kakaomobility_detail.json"))
    assert p.company == "kakaomobility"
    assert p.apply_url == "https://kakaomobility.career.greetinghr.com/ko/o/236686"
    assert p.deadline is None
    assert p.category == "기술"
    assert "카카오내비" in p.description and "<" not in p.description


def test_greetinghr_base_is_not_registered():
    assert "upstage" in REGISTRY and "kakaopay" in REGISTRY
    assert all(not issubclass(c, greetinghr.GreetingHRScraper) or c.company in ("upstage", "kakaopay", "kakaomobility") for c in REGISTRY.values())


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


# --- dunamu (Next.js RSC payload) ---

def test_dunamu_parse_list_and_keep():
    jobs = dunamu.parse_list((FIX / "dunamu_list.rsc").read_bytes())
    assert jobs and all({"id", "name", "jobGroupCode"} <= set(j) for j in jobs)
    kept = [j for j in jobs if dunamu.keep(j)]
    assert kept and len(kept) < len(jobs)
    assert not any(j["jobGroupCode"] == "T_TALENT_POOL" for j in kept)
    with pytest.raises(ValueError):
        dunamu.parse_list(b"0:{}\n")


def test_dunamu_text_chunks_use_utf8_byte_length_without_newlines():
    rsc = "1d:T5,abcde2d:T8,한글\nx2e:I[1]\n".encode()  # 한글 = 6 bytes, 청크 뒤에 개행 없이 다음 행
    assert dunamu.text_chunks(rsc) == {"1d": "abcde", "2d": "한글\nx"}


def test_dunamu_parse_detail_picks_resolvable_ref():
    rsc = (FIX / "dunamu_detail.rsc").read_bytes()
    pid = int(re.search(rb'"positionId":(\d+)', rsc).group(1))
    refs = [r.decode() for r in re.findall(rb'"jobNoticeContent":"\$([0-9a-f]+)"', rsc)]
    assert len(refs) == 2 and sum(r in dunamu.text_chunks(rsc) for r in refs) == 1
    detail = dunamu.parse_detail(rsc, pid)
    assert detail["positionId"] == pid and detail["jobNoticeContent"].startswith("<")
    job = {"id": pid, "name": detail["jobNoticeName"], "jobGroupCode": detail["jobGroupCode"],
           "experienceLevel": detail["experienceLevel"]}
    p = dunamu.to_posting(job, detail)
    assert p.company == "dunamu" and p.apply_url == f"https://careers.dunamu.com/detail/{pid}"
    assert p.category == f"{detail['jobGroupCode']}/{detail['experienceLevel']}"
    assert p.description and "<" not in p.description and len(p.description) > 300
    assert "두나무 소개" in p.description
    with pytest.raises(KeyError):
        dunamu.parse_detail(rsc, -1)


def test_dunamu_parse_detail_falls_back_to_empty_body():
    rsc = (FIX / "dunamu_detail.rsc").read_bytes()
    pid = int(re.search(rb'"positionId":(\d+)', rsc).group(1))
    without_chunk = b"\n".join(line for line in rsc.split(b"\n") if not re.match(rb"^[0-9a-f]+:T", line))
    assert dunamu.parse_detail(without_chunk, pid)["jobNoticeContent"] == ""


# --- nhn (REST API) ---

def test_nhn_keep_and_to_posting():
    jobs = load("nhn_list.json")["result"]
    kept = [j for j in jobs if nhn.keep(j)]
    assert kept and len(kept) < len(jobs)
    job = next(j for j in jobs if j["id"] == "4413318345634587442")
    p = nhn.to_posting(job, load("nhn_detail.json")["result"])
    assert p.company == "nhn" and p.external_id == job["id"]
    assert p.apply_url == f"https://careers.nhn.com/recruits/{job['id']}"
    assert p.deadline is None
    assert p.category.startswith(f"{job['corporation']['name']}/")
    assert p.description and "<" not in p.description and len(p.description) > 300


def test_nhn_deadline_and_description_edge_cases():
    assert nhn.deadline("2999-12-31T23:59:00") is None
    assert nhn.deadline("2026-10-19T23:59:00") == date(2026, 10, 19)
    assert nhn.deadline(None) is None
    assert nhn.description({"jobPostingContentsItems": None}) is None
    assert not nhn.keep({"jobSeries": None})


def test_nhn_category_dedupes_job_series():
    job = dict(load("nhn_list.json")["result"][0])
    tech = {"name": "Backend", "jobGroup": {"name": "Tech"}}
    job["jobSeries"] = [tech, tech, {"name": "Sales", "jobGroup": {"name": "Business"}}]
    assert nhn.to_posting(job, {}).category == f"{job['corporation']['name']}/Backend"
