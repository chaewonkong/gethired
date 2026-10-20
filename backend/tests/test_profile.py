import asyncio
import shutil
from pathlib import Path

import pytest

from app import profile
from app.llm import LLMResult
from app.profile import ROLES, Profile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

PROFILE_DATA = {"name": "t", "seniority": "mid", "years_experience": 5, "core_skills": ["Go"], "familiar_skills": [],
                "weak_or_learning": [], "domains": ["matchmaking"], "notable_achievements": [],
                "preferences": {"locations": [], "visa_or_work_authorization": None, "target_domains": [],
                                "target_roles": []},
                "dealbreakers": [], "summary": "s"}


@pytest.fixture
def resume_dir(tmp_path, monkeypatch):
    d = tmp_path / "resume"
    d.mkdir()
    monkeypatch.setattr(profile, "RESUME_DIR", d)
    return d


def fake_ask_json(captured: dict, data: dict = PROFILE_DATA):
    async def ask_json(prompt, schema, system_prompt=None):
        captured["prompt"] = prompt
        captured["calls"] = captured.get("calls", 0) + 1
        return LLMResult(data=data, cost_usd=0, duration_ms=0, input_tokens=0, output_tokens=0)
    return ask_json


class CacheRepo:
    def __init__(self, cached: dict | None = None):
        self.cached = cached
        self.saved: dict | None = None

    def get_profile_cache(self, h):
        return self.cached

    def set_profile_cache(self, h, data, now):
        self.saved = data


def test_source_files_md_and_pdf_sorted(resume_dir):
    (resume_dir / "b.md").write_text("b")
    shutil.copy(FIXTURES / "resume_sample.pdf", resume_dir / "a.pdf")
    (resume_dir / ".a.pdf.tmp").write_bytes(b"x")
    (resume_dir / "c.txt").write_text("c")
    assert [f.name for f in profile.source_files()] == ["a.pdf", "b.md"]


def test_extract_prompt_contains_both_documents(resume_dir, monkeypatch):
    (resume_dir / "notes.md").write_text("# Notes\nPrefers Canada")
    shutil.copy(FIXTURES / "resume_sample.pdf", resume_dir / "cv.pdf")
    captured: dict = {}
    monkeypatch.setattr(profile, "ask_json", fake_ask_json(captured))
    result = asyncio.run(profile.extract(profile.source_files()))
    assert result.core_skills == ["Go"]
    prompt = captured["prompt"]
    assert '<document name="cv.pdf">\nBackend Engineer, 5 years, Go Redis Kubernetes' in prompt
    assert '<document name="notes.md">\n# Notes\nPrefers Canada\n</document>' in prompt
    assert prompt.index("cv.pdf") < prompt.index("notes.md")


def test_source_hash_tracks_pdf_bytes(resume_dir):
    pdf = resume_dir / "cv.pdf"
    shutil.copy(FIXTURES / "resume_sample.pdf", pdf)
    h1 = profile.source_hash()
    assert profile.source_hash() == h1
    data = pdf.read_bytes()
    pdf.write_bytes(data.replace(b"Go Redis", b"Go Kafka"))
    h2 = profile.source_hash()
    assert h2 != h1
    (resume_dir / "big.md").write_bytes(b"y" * (3 * 1024 * 1024 + 7))
    assert profile.source_hash() not in (h1, h2)


def test_get_profile_requires_files(resume_dir):
    class Repo:
        def get_profile_cache(self, h):
            return None

    with pytest.raises(FileNotFoundError, match=r"no \*\.md / \*\.pdf files"):
        asyncio.run(profile.get_profile(Repo()))


def test_profile_schema_roles_enum():
    items = Profile.model_json_schema()["properties"]["roles"]["items"]
    assert items["enum"] == list(ROLES)
    assert len(ROLES) == 15
    assert "roles" not in Profile.model_json_schema()["required"]


def test_profile_without_roles_loads_with_default():
    assert Profile.model_validate(PROFILE_DATA).roles == []


def test_cached_profile_without_roles_is_reextracted(resume_dir, monkeypatch):
    (resume_dir / "cv.md").write_text("Backend Engineer")
    captured: dict = {}
    monkeypatch.setattr(profile, "ask_json", fake_ask_json(captured, {**PROFILE_DATA, "roles": ["backend"]}))
    repo = CacheRepo(cached=dict(PROFILE_DATA))
    result = asyncio.run(profile.get_profile(repo))
    assert captured["calls"] == 1
    assert result.roles == ["backend"]
    assert repo.saved["roles"] == ["backend"]


def test_cached_profile_with_roles_is_reused(resume_dir, monkeypatch):
    (resume_dir / "cv.md").write_text("Backend Engineer")
    captured: dict = {}
    monkeypatch.setattr(profile, "ask_json", fake_ask_json(captured))
    repo = CacheRepo(cached={**PROFILE_DATA, "roles": ["backend"]})
    result = asyncio.run(profile.get_profile(repo))
    assert "calls" not in captured
    assert result.roles == ["backend"]
    assert repo.saved is None


def test_profile_system_prompt():
    assert "프론트엔드 전담" not in profile.SYSTEM
    assert "roles:" in profile.SYSTEM
