import json
from datetime import date
from pathlib import Path

from app.scrapers import REGISTRY, hyundai, samsung

FIX = Path(__file__).parent.parent / "fixtures"


def test_registry_includes_new_companies():
    assert {"samsung", "hyundai"} <= set(REGISTRY)


def test_samsung_list_and_detail():
    seqnos, max_page = samsung.parse_list((FIX / "samsung_list.html").read_text())
    assert seqnos and max_page == 1 and all(s.isdigit() for s in seqnos)
    assert len(seqnos) == len(set(seqnos))

    detail = json.loads((FIX / "samsung_detail.json").read_text())
    postings = samsung.parse_detail(detail, "23285")
    assert len(postings) == 1
    p = postings[0]
    assert p.company == "samsung" and p.external_id == "23285-14013"
    assert p.apply_url == "https://www.samsungcareers.com/hr/?no=23285"
    assert p.deadline == date(2026, 10, 16)
    assert "[담당업무]" in p.description and "[자격요건]" in p.description
    assert "삼성전자" in p.category

    other = json.loads(json.dumps(detail))
    other["data"]["result"]["cmpNameKr"] = "삼성생명"
    other["data"]["result"]["title"] = "경력사원 채용"
    assert samsung.parse_detail(other, "1") == []


def test_hyundai_list_filters_engineering_sectors():
    data = json.loads((FIX / "hyundai_list.json").read_text())
    postings = hyundai.parse_list(data)
    assert postings
    assert all(p.category.split("/")[0] in hyundai.ENGINEERING_SECTORS for p in postings)
    assert len(postings) < len(data["data"]["list"])
    p = postings[0]
    assert p.external_id.count("-") == 2 and p.apply_url.startswith("https://talent.hyundai.com/apply/applyView.hc?")
    assert p.deadline is not None and "부문:" in p.description
