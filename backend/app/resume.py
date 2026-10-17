import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from starlette.concurrency import run_in_threadpool

TEXT_LIMIT = 50_000
EXTENSIONS = (".md", ".pdf")


def _path(resume_dir: Path, name: str) -> Path:
    base = Path(name).name
    if base != name or base.startswith("."):
        raise ValueError(f"invalid resume file name: {name}")
    if not base.endswith(EXTENSIONS):
        raise ValueError(f"md 또는 pdf 파일만 업로드할 수 있습니다: {name}")
    return resume_dir / base


def extract_text(path: Path) -> str:
    """md는 그대로, pdf는 페이지 텍스트를 이어 붙인다. 텍스트가 없으면 "". 깨진 pdf는 ValueError"""
    if path.suffix == ".pdf":
        try:
            pages = [page.extract_text() or "" for page in PdfReader(path).pages]
        except (PyPdfError, ValueError, OSError, KeyError, TypeError, IndexError) as e:
            raise ValueError(f"cannot read pdf: {path.name}: {e}") from e
        text = "\n".join(pages)
    else:
        text = path.read_text()
    if not text.strip():
        return ""
    if len(text) > TEXT_LIMIT:
        return text[:TEXT_LIMIT] + "\n[이하 생략]"
    return text


def list_files(resume_dir: Path) -> list[dict[str, Any]]:
    if not resume_dir.is_dir():
        return []
    files = sorted(f for f in resume_dir.iterdir()
                   if f.is_file() and f.suffix in EXTENSIONS and not f.name.startswith("."))
    return [
        {"name": f.name, "size": f.stat().st_size,
         "updated_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
        for f in files
    ]


async def save(resume_dir: Path, name: str, chunks: AsyncIterator[bytes]) -> None:
    """임시 dotfile에 스트리밍 후 교체. 텍스트 없는 pdf는 저장하지 않고 ValueError"""
    path = _path(resume_dir, name)
    resume_dir.mkdir(parents=True, exist_ok=True)
    tmp = resume_dir / f".{path.name}.tmp"
    try:
        with tmp.open("wb") as f:
            async for chunk in chunks:
                f.write(chunk)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if path.suffix == ".pdf":
        try:
            text = await run_in_threadpool(extract_text, path)
        except ValueError:
            path.unlink(missing_ok=True)
            raise
        if not text:
            path.unlink(missing_ok=True)
            raise ValueError(f"텍스트를 추출할 수 없는 PDF입니다 (스캔·이미지 PDF): {name}")


def delete(resume_dir: Path, name: str) -> bool:
    """파일이 없으면 False"""
    path = _path(resume_dir, name)
    if not path.is_file():
        return False
    path.unlink()
    return True
