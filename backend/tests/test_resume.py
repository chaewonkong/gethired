from pathlib import Path

import pytest

from app import resume

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_extract_pdf_text():
    text = resume.extract_text(FIXTURES / "resume_sample.pdf")
    assert "Backend Engineer, 5 years, Go Redis Kubernetes" in text
    assert "Working holiday visa" in text
    assert text.index("Go Redis") < text.index("Working holiday")


def test_extract_blank_pdf_is_empty():
    assert resume.extract_text(FIXTURES / "resume_blank.pdf") == ""


def test_extract_md_passthrough(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# hi\n\nbody")
    assert resume.extract_text(f) == "# hi\n\nbody"
    (tmp_path / "ws.md").write_text(" \n\t\n")
    assert resume.extract_text(tmp_path / "ws.md") == ""


def test_extract_truncates_with_marker(tmp_path):
    f = tmp_path / "big.md"
    f.write_text("x" * (resume.TEXT_LIMIT + 10))
    text = resume.extract_text(f)
    assert text == "x" * resume.TEXT_LIMIT + "\n[이하 생략]"
    (tmp_path / "exact.md").write_text("y" * resume.TEXT_LIMIT)
    assert resume.extract_text(tmp_path / "exact.md") == "y" * resume.TEXT_LIMIT


def test_extract_corrupt_pdf_raises(tmp_path):
    f = tmp_path / "bad.pdf"
    f.write_bytes(b"%PDF-1.4\nthis is not really a pdf")
    with pytest.raises(ValueError):
        resume.extract_text(f)
    (tmp_path / "text.pdf").write_bytes(b"plain text pretending to be pdf")
    with pytest.raises(ValueError):
        resume.extract_text(tmp_path / "text.pdf")
