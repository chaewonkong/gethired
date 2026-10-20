import asyncio

import pytest

from app import feedback
from app.llm import LLMError, LLMResult
from app.profile import Preferences, Profile

PROFILE = Profile(name="t", seniority="senior", years_experience=5, core_skills=["Go", "Redis"], familiar_skills=[],
                  weak_or_learning=[], domains=["matchmaking"], notable_achievements=["ClickHouse 마이그레이션"],
                  preferences=Preferences(locations=[], visa_or_work_authorization=None, target_domains=[],
                                          target_roles=[]),
                  dealbreakers=[], summary="s")

POSTING = {"id": 1, "company": "a", "title": "Backend", "summary": "요약문", "gaps": ["Kafka 경험 없음"],
           "requirements": [{"text": "Go 3년 이상", "fit": "met"}], "preferred": [{"text": "Kafka 운영 경험", "fit": "unmet"}], "description": "본문" * 4000}


def fake_ask(items: list[str], calls: list):
    async def ask_json(prompt, schema, system_prompt=None):
        calls.append((prompt, schema, system_prompt))
        return LLMResult(data={"items": items}, cost_usd=0.01, duration_ms=1, input_tokens=1, output_tokens=1)
    return ask_json


def run(monkeypatch, items, posting=POSTING):
    calls: list = []
    monkeypatch.setattr(feedback, "ask_json", fake_ask(items, calls))
    return asyncio.run(feedback.generate(PROFILE, posting)), calls


def test_prompt_has_profile_full_body_gaps_and_system(monkeypatch):
    (items, res), calls = run(monkeypatch, ["a: 1", "b: 2", "c: 3"])
    assert items == ["a: 1", "b: 2", "c: 3"] and res.cost_usd == 0.01
    prompt, schema, system = calls[0]
    assert system == feedback.SYSTEM
    assert schema == feedback.Feedback.model_json_schema()
    assert "ClickHouse 마이그레이션" in prompt
    assert POSTING["description"] in prompt  # DESC_LIMIT 없이 전부
    assert "Kafka 경험 없음" in prompt and "Go 3년 이상 [met]" in prompt and "Kafka 운영 경험 [unmet]" in prompt


def test_legacy_posting_without_description_uses_summary_and_requirements(monkeypatch):
    legacy = {**POSTING, "description": None, "requirements": None, "preferred": None}
    _, calls = run(monkeypatch, ["a: 1"], legacy)
    assert "본문" not in calls[0][0] and "요약문" in calls[0][0] and "Kafka 경험 없음" in calls[0][0]

    _, calls = run(monkeypatch, ["a: 1"], {**POSTING, "description": None})
    assert "본문" not in calls[0][0] and "요약문" in calls[0][0] and "Go 3년 이상" in calls[0][0]


def test_items_truncated_to_max_and_empty_is_error(monkeypatch):
    (items, _), _ = run(monkeypatch, [f"항목{i}: 설명" for i in range(6)])
    assert items == [f"항목{i}: 설명" for i in range(feedback.FEEDBACK_MAX_ITEMS)]
    (items, _), _ = run(monkeypatch, ["a: 1", "b: 2"])
    assert items == ["a: 1", "b: 2"]
    with pytest.raises(LLMError):
        run(monkeypatch, [])


def test_system_prompt_rules():
    for phrase in ("3~5개", "항목: 설명", "지어내", "일반론", "gaps"):
        assert phrase in feedback.SYSTEM
