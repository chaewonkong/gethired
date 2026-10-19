import json
import re
from pathlib import Path

from app.scrapers.moloco import MolocoScraper

FIX = Path(__file__).parent.parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def test_moloco_parse():
    data = load("moloco_greenhouse.json")
    ps = MolocoScraper().parse(data)
    assert 0 < len(ps) < len(data["jobs"])
    assert all(p.company == "moloco" for p in ps)
    assert len({p.external_id for p in ps}) == len(ps)
    assert all(p.apply_url.startswith("https://job-boards.greenhouse.io/") for p in ps)


def test_moloco_filters_location_and_eoi():
    ps = MolocoScraper().parse(load("moloco_greenhouse.json"))
    assert all(re.search(r"Seoul|Korea|Canada|Toronto", p.raw["location"]["name"]) for p in ps)
    assert not any(p.title.lower().startswith("expression of interest") for p in ps)


def test_moloco_keeps_seoul_scientist():
    data = load("moloco_greenhouse.json")
    scientists = {
        str(j["id"]) for j in data["jobs"]
        if "Scientist" in j["title"] and "Seoul" in j["location"]["name"]
    }
    kept = {p.external_id for p in MolocoScraper().parse(data)}
    assert scientists <= kept


def test_moloco_description_and_category():
    p = MolocoScraper().parse(load("moloco_greenhouse.json"))[0]
    assert p.description and "<" not in p.description and len(p.description) > 300
    assert p.deadline is None
    assert p.category
