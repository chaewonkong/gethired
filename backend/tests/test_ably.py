"""에이블리(Ninehire) 파서 테스트 (fixtures/ 저장 응답 기반)."""
import json
from datetime import date
from pathlib import Path

from app.scrapers.ably import AblyScraper
from app.scrapers.base import REGISTRY
from app.scrapers.ninehire import NinehireScraper

FIX = Path(__file__).parent.parent / "fixtures"
DETAIL_ID = "7ab9f5c0-bca1-11f1-ba60-79120a03fe8d"


def load(name: str):
    return json.loads((FIX / name).read_text())


def test_ably_keep_engineering_only():
    jobs = load("ably_list.json")["results"]
    s = AblyScraper()
    kept = [j for j in jobs if s.keep(j)]
    assert kept and len(kept) < len(jobs)
    assert all(j["jobGroup"]["title"] == "Engineering" and not j["isPrivate"] for j in kept)
    assert not s.keep({**kept[0], "jobGroup": None})
    assert not s.keep({**kept[0], "isPrivate": True})


def test_ably_to_posting():
    job = next(j for j in load("ably_list.json")["results"] if j["recruitmentId"] == DETAIL_ID)
    p = AblyScraper().to_posting(job, load("ably_detail.json"))
    assert p.company == "ably"
    assert p.external_id == DETAIL_ID
    assert p.title == (job["externalTitle"] or job["title"]).strip()
    assert p.apply_url == f"https://tydtr0dj.ninehire.site/job_posting/{job['addressKey']}"
    assert p.deadline is None
    assert p.category == "Engineering"
    assert p.description and "<" not in p.description and len(p.description) > 500


def test_ably_deadline():
    job = next(j for j in load("ably_list.json")["results"] if j["recruitmentId"] == DETAIL_ID)
    p = AblyScraper().to_posting({**job, "deadlineValue": "2026-12-31T14:59:59Z"}, load("ably_detail.json"))
    assert p.deadline == date(2026, 12, 31)


def test_ninehire_base_not_registered():
    assert REGISTRY["ably"] is AblyScraper
    assert NinehireScraper not in REGISTRY.values()
