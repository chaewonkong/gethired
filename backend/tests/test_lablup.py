import json
from pathlib import Path

from app.scrapers import lablup

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def next_data_html(props: dict) -> str:
    payload = json.dumps({"props": {"pageProps": props}}, ensure_ascii=False)
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{payload}</script></body></html>'


def test_parse_list_and_detail():
    positions = load("lablup_list.json")
    detail = load("lablup_detail.json")
    assert lablup.parse_list(next_data_html({"positions": positions})) == positions["contents"]
    assert lablup.parse_detail(next_data_html({"positionDetail": detail})) == detail


def test_keep_filters_by_category_id():
    jobs = load("lablup_list.json")["contents"]
    assert [j for j in jobs if lablup.keep(j)]
    sales = {**jobs[0], "category": {"id": 1, "name": "세일즈", "categoryId": "SALES"}}
    solution = {**jobs[0], "category": {"id": 32, "name": "솔루션", "categoryId": "SOLUTION"}}
    assert not lablup.keep(sales)
    assert lablup.keep(solution)
    assert not lablup.keep({**jobs[0], "category": None})


def test_to_posting():
    detail = load("lablup_detail.json")
    job = next(j for j in load("lablup_list.json")["contents"] if j["positionId"] == detail["positionId"])
    p = lablup.to_posting(job, detail)
    assert p.company == "lablup"
    assert p.external_id == job["positionId"]
    assert p.apply_url == f"https://www.lablup.com/ko/careers/{job['positionId']}"
    assert p.deadline is None
    assert p.title == p.title.strip()
    assert p.category.startswith(job["category"]["categoryId"])
    assert len(p.description) > 300
    assert "Backend.AI" in p.description
    assert "*   " not in p.description
