import json
from datetime import date
from pathlib import Path

import pytest

from scrapers import REGISTRY, RawPosting, kakao, line, naver
from scrapers.coupang import CoupangScraper
from scrapers.daangn import DaangnScraper
from scrapers.toss import ENGINEERING_CATEGORIES, TossScraper

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def assert_required(postings: list[RawPosting], company: str):
    assert postings, "no postings parsed"
    assert all(p.company == company for p in postings)
    assert len({p.external_id for p in postings}) == len(postings)
    assert all(p.title and p.apply_url.startswith("http") for p in postings)


def test_registry_has_six():
    assert set(REGISTRY) == {"naver", "kakao", "coupang", "toss", "daangn", "line"}


def test_naver_list_filters_tech_and_parses_date():
    jobs = naver.parse_list(load("naver_list.json"))
    assert jobs and all(j["classCdNm"] == "Tech" for j in jobs)
    p = naver.to_posting(jobs[0], None)
    assert p.deadline == date(2026, 10, 12)
    assert p.category.startswith("Tech/")
    assert_required([naver.to_posting(j, None) for j in jobs], "naver")


def test_naver_detail_extracts_boxes():
    text = naver.parse_detail((FIX / "naver_view.html").read_text())
    assert text and "Who We Are" in text and "Required Skills" in text
    assert "<" not in text


def test_kakao_page():
    postings = kakao.parse_page(load("kakao_page1.json"))
    assert_required(postings, "kakao")
    assert all(p.apply_url == f"https://careers.kakao.com/jobs/{p.external_id}" for p in postings)
    assert all(p.description and len(p.description) > 100 for p in postings)
    assert all(p.category.startswith("TECHNOLOGY") for p in postings)


def test_coupang_keeps_korea_engineering_only():
    data = load("coupang.json")
    postings = CoupangScraper().parse(data)
    assert_required(postings, "coupang")
    assert len(postings) < len(data["jobs"])
    raw_by_id = {str(j["id"]): j for j in data["jobs"]}
    assert all("Korea" in raw_by_id[p.external_id]["location"]["name"] for p in postings)
    assert all(p.description for p in postings)


def test_toss_categories_and_description_from_metadata():
    postings = TossScraper().parse(load("toss.json"))
    assert_required(postings, "toss")
    assert {p.category for p in postings} <= ENGINEERING_CATEGORIES
    assert all(p.description and len(p.description) > 100 for p in postings)


def test_daangn_division_tech():
    postings = DaangnScraper().parse(load("daangn.json"))
    assert_required(postings, "daangn")
    assert all(p.category == "Tech" for p in postings)
    assert all(p.description for p in postings)


def test_line_list_and_detail():
    nodes = line.parse_list(load("line_list.json"))
    assert nodes and all(any(u["name"] == "Engineering" for u in n["job_unit"]) for n in nodes)
    assert all(n["publish"] for n in nodes)
    detail = load("line_detail.json")
    node = next(n for n in nodes if n["strapiId"] == detail["result"]["data"]["strapiJobs"]["strapiId"])
    p = line.to_posting(node, detail)
    assert p.description and len(p.description) > 100
    assert p.apply_url.startswith("http")
    assert p.category.startswith("Engineering/")


@pytest.mark.parametrize("until_filled,end_date,expected", [
    (True, "2026-10-31T14:59:00.000Z", None),
    (False, "2026-10-31T14:59:00.000Z", date(2026, 10, 31)),
    (False, None, None),
])
def test_line_deadline_rules(until_filled, end_date, expected):
    node = {"strapiId": 1, "title": "t", "until_filled": until_filled, "end_date": end_date,
            "job_fields": [], "job_unit": [{"name": "Engineering"}]}
    assert line.to_posting(node, None).deadline == expected
