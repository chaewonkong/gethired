import asyncio
import json

import pytest
from pydantic import ValidationError

from app import matcher
from app.llm import LLMResult
from app.matcher import ADJACENT, GAP_KINDS, SYSTEM, Batch, Breakdown, Match, level_for
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
        assert f"- {role}: {', '.join(adj) or '(없음)'}" in SYSTEM
    for role in ROLES:
        assert role in SYSTEM
    assert "role" in GAP_KINDS
    assert ", ".join(GAP_KINDS) in SYSTEM


def test_batch_accepts_role_gap():
    m = Match(external_id="1", fit_level="stretch", score=50, gaps=["role: iOS 전담, 지원자는 웹 프론트엔드"],
              summary="iOS 앱을 만드는 포지션", tech_stack=["Swift"], fit_reason="웹 프론트 경력은 있으나 iOS 경험이 없다.",
              requirements=[], preferred=[], breakdown=Breakdown(skills=20, domain=20, seniority=10, preferred=0))
    assert Batch(matches=[m]).matches[0].gaps[0].startswith("role:")


def match_data(**kw) -> dict:
    base = {"external_id": "p1", "fit_level": "strong", "score": 90,
            "breakdown": {"skills": 35, "domain": 35, "seniority": 15, "preferred": 5}, "gaps": [],
            "summary": "웹 프론트엔드 포지션", "tech_stack": ["React"], "requirements": [{"text": "React 3년 이상", "fit": "met"}],
            "preferred": [{"text": "TypeScript", "fit": "partial"}], "fit_reason": "React 4년 경력이 공고의 핵심 요건과 정확히 맞는다."}
    return {**base, **kw}


def test_normalize_breakdown_total_overrides_score_and_level():
    m = Match.model_validate(match_data(score=90, fit_level="strong",
                                        breakdown={"skills": 20, "domain": 20, "seniority": 10, "preferred": 0}))
    m.normalize()
    assert (m.score, m.fit_level) == (50, "stretch")


def test_normalize_keeps_consistent_match():
    m = Match.model_validate(match_data())
    m.normalize()
    assert (m.score, m.fit_level, m.breakdown.total) == (90, "strong", 90)


def test_normalize_clamps_out_of_range_axes_without_validation_error():
    m = Match.model_validate(match_data(score=90, breakdown={"skills": 40, "domain": 35, "seniority": -3, "preferred": 12}))
    m.normalize()
    assert m.breakdown.model_dump() == {"skills": 35, "domain": 35, "seniority": 0, "preferred": 10}
    assert (m.score, m.fit_level) == (80, "strong")


def test_normalize_truncates_lists():
    m = Match.model_validate(match_data(requirements=[{"text": f"요건 {i} " + "x" * 100, "fit": "met"} for i in range(10)],
                                        preferred=[{"text": "a", "fit": "unmet"}] * 9))
    m.normalize()
    assert len(m.requirements) == 8 and all(len(r.text) == 80 and r.fit == "met" for r in m.requirements)
    assert len(m.preferred) == 8


def test_requirement_fit_is_enum():
    with pytest.raises(ValidationError):
        Match.model_validate(match_data(requirements=[{"text": "x", "fit": "maybe"}]))
    with pytest.raises(ValidationError):
        Match.model_validate(match_data(requirements=["문자열만"]))


def test_system_prompt_mentions_new_outputs():
    for needle in ("breakdown", "requirements", "preferred", "80자", "8개", "합계 = score", "met", "partial", "unmet"):
        assert needle in SYSTEM


def test_render_uses_6000_char_limit():
    p = RawPosting(company="toss", external_id="p1", title="t", apply_url="https://x", description="x" * 7000)
    body = matcher.render(p).split("본문:\n")[1].split("\n</posting>")[0]
    assert len(body) == 6000 and matcher.DESC_LIMIT == 6000


def test_to_row_includes_description_and_new_fields():
    p = RawPosting(company="toss", external_id="p1", title="t", apply_url="https://x", description="본문")
    row = matcher.to_row(p, Match.model_validate(match_data()), "T1")
    assert row["description"] == "본문" and row["requirements"] == [{"text": "React 3년 이상", "fit": "met"}]
    assert row["preferred"] == [{"text": "TypeScript", "fit": "partial"}]
    assert row["breakdown"] == {"skills": 35, "domain": 35, "seniority": 15, "preferred": 5}
    p2 = RawPosting(company="toss", external_id="p2", title="t", apply_url="https://x")
    assert matcher.to_row(p2, Match.model_validate(match_data()), "T1")["description"] is None


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
        return LLMResult(data={"matches": [match_data()]}, cost_usd=0, duration_ms=0, input_tokens=0, output_tokens=0)

    monkeypatch.setattr(matcher, "ask_json", ask_json)
    matches, results = asyncio.run(matcher.judge_batch(profile, [posting], asyncio.Semaphore(1)))
    assert captured["system"] == SYSTEM
    assert json.loads(captured["prompt"].split("<profile>\n")[1].split("\n</profile>")[0])["roles"] == ["frontend"]
    assert [m.external_id for m in matches] == ["p1"] and len(results) == 1
