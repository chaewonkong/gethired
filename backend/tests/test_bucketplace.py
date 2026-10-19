"""오늘의집(버킷플레이스) 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
from pathlib import Path

from app.scrapers import bucketplace

FIX = Path(__file__).parent.parent / "fixtures"
DETAIL_ID = "216240"


def load(name: str):
    return json.loads((FIX / name).read_text())


def test_bucketplace_list_keeps_engineering():
    jobs = bucketplace.parse_list(load("bucketplace_list.json"))
    kept = [j for j in jobs if bucketplace.keep(j)]
    assert kept and len(kept) < len(jobs)
    assert all(j["teamName"] == "Engineering" for j in kept)


def test_bucketplace_opening_id():
    assert bucketplace.opening_id({"recruitUrl": "https://bucketplace.career.greetinghr.com/ko/o/198761"}) == "198761"
    assert bucketplace.opening_id({"recruitUrl": "https://bucketplace.career.greetinghr.com/o/123"}) == "123"
    assert bucketplace.opening_id({"recruitUrl": "https://bucketplace.career.greetinghr.com/"}) is None
    assert bucketplace.opening_id({}) is None


def test_bucketplace_to_posting():
    jobs = bucketplace.parse_list(load("bucketplace_list.json"))
    job = next(j for j in jobs if bucketplace.opening_id(j) == DETAIL_ID)
    p = bucketplace.to_posting(job, load("bucketplace_detail.json"))
    assert p.company == "bucketplace"
    assert p.external_id == DETAIL_ID
    assert p.title == job["name"].strip()
    assert p.apply_url == f"https://bucketplace.career.greetinghr.com/ko/o/{DETAIL_ID}"
    assert p.deadline is None
    assert p.description and "<" not in p.description and len(p.description) > 300
    assert p.category.startswith("Engineering")
