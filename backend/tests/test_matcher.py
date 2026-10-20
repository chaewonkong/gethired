import asyncio
import json

import pytest

from app import matcher
from app.llm import LLMResult
from app.matcher import ADJACENT, GAP_KINDS, SYSTEM, Batch, Match, level_for
from app.profile import ROLES, Preferences, Profile
from app.scrapers import RawPosting


@pytest.mark.parametrize("score,level", [(80, "strong"), (79, "good"), (65, "good"), (64, "stretch"),
                                         (45, "stretch"), (44, "exclude"), (0, "exclude")])
def test_level_for_boundaries(score, level):
    assert level_for(score) == level


def test_adjacent_table_complete_and_symmetric():
    assert set(ADJACENT) == set(ROLES)
    for role, adj in ADJACENT.items():
        assert role not in adj
        assert set(adj) <= set(ROLES)
        assert len(set(adj)) == len(adj)
        for other in adj:
            assert role in ADJACENT[other], f"{role}->{other} 비대칭"


def test_system_prompt_is_role_neutral():
    assert "프론트엔드 전담" not in SYSTEM
    assert "백엔드/서버/플랫폼/데이터 엔지니어링이면 exclude로 보내지 않습니다" not in SYSTEM
    for role, adj in ADJACENT.items():
        assert f"- {role}: {', '.join(adj)}" in SYSTEM
    for role in ROLES:
        assert role in SYSTEM
    assert "role" in GAP_KINDS
    assert ", ".join(GAP_KINDS) in SYSTEM


def test_batch_accepts_role_gap():
    m = Match(external_id="1", fit_level="stretch", score=50, gaps=["role: iOS 전담, 지원자는 웹 프론트엔드"],
              summary="iOS 앱을 만드는 포지션", tech_stack=["Swift"], fit_reason="웹 프론트 경력은 있으나 iOS 경험이 없다.")
    assert Batch(matches=[m]).matches[0].gaps[0].startswith("role:")


def test_judge_batch_sends_roles_and_system(monkeypatch):
    profile = Profile(name=None, seniority="mid", roles=["frontend"], years_experience=4, core_skills=["React"],
                      familiar_skills=[], weak_or_learning=[], domains=["commerce"], notable_achievements=[],
                      preferences=Preferences(locations=[], visa_or_work_authorization=None, target_domains=[],
                                              target_roles=[]),
                      dealbreakers=[], summary="s")
    posting = RawPosting(company="toss", external_id="p1", title="Frontend Engineer", apply_url="https://x",
                         description="React", category="Frontend")
    captured: dict = {}

    async def ask_json(prompt, schema, system_prompt=None):
        captured["prompt"], captured["system"] = prompt, system_prompt
        data = {"matches": [{"external_id": "p1", "fit_level": "strong", "score": 90, "gaps": [],
                             "summary": "웹 프론트엔드 포지션", "tech_stack": ["React"],
                             "fit_reason": "React 4년 경력이 공고의 핵심 요건과 정확히 맞는다."}]}
        return LLMResult(data=data, cost_usd=0, duration_ms=0, input_tokens=0, output_tokens=0)

    monkeypatch.setattr(matcher, "ask_json", ask_json)
    matches, results = asyncio.run(matcher.judge_batch(profile, [posting], asyncio.Semaphore(1)))
    assert captured["system"] == SYSTEM
    assert json.loads(captured["prompt"].split("<profile>\n")[1].split("\n</profile>")[0])["roles"] == ["frontend"]
    assert [m.external_id for m in matches] == ["p1"] and len(results) == 1
