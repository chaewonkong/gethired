import asyncio
import shutil
from pathlib import Path

import pytest

from app import profile
from app.llm import LLMResult

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


def fake_ask_json(captured: dict):
    async def ask_json(prompt, schema, system_prompt=None):
        captured["prompt"] = prompt
        return LLMResult(data=PROFILE_DATA, cost_usd=0, duration_ms=0, input_tokens=0, output_tokens=0)
    return ask_json


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
