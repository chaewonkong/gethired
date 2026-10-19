"""크래프톤 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
from pathlib import Path

import pytest

from app.scrapers.krafton import TECH_DEPARTMENTS, KraftonScraper

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def job(location: str, department: str) -> dict:
    return {"location": {"name": location}, "departments": [{"name": department}]}


def test_krafton_parses_bluehole():
    data = load("krafton_greenhouse_bluehole.json")
    postings = KraftonScraper().parse(data)
    assert postings and len(postings) < len(data["jobs"])
    assert all(p.company == "krafton" for p in postings)
    assert len({p.external_id for p in postings}) == len(postings)
    assert all(p.apply_url.startswith("https://job-boards.greenhouse.io/") for p in postings)
    assert all({d["name"] for d in p.raw["departments"]} & TECH_DEPARTMENTS for p in postings)


def test_krafton_drops_non_korea_locations():
    data = load("krafton_greenhouse_ludorobotics.json")
    assert any("San Francisco" in j["location"]["name"] for j in data["jobs"])
    postings = KraftonScraper().parse(data)
    assert postings
    assert all("San Francisco" not in p.raw["location"]["name"] for p in postings)


@pytest.mark.parametrize("location, department, kept", [
    ("seoul", "Tech", True),
    ("San Francisco", "Tech", False),
    ("Seoul", "Engineering", False),
    ("Pangyo", "Data", True),
    ("Seoul; Seoul, South Korea", "IT Infra", True),
])
def test_krafton_keep(location, department, kept):
    assert KraftonScraper().keep(job(location, department)) is kept


def test_krafton_category_and_description():
    p = next(p for p in KraftonScraper().parse(load("krafton_greenhouse_bluehole.json")) if p.external_id == "8511473002")
    assert p.category == "Bluehole Studio/Server Programming"
    assert p.description and "<" not in p.description and len(p.description) > 200
    assert p.deadline is None
