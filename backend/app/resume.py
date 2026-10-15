from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BYTES = 1024 * 1024


def _path(resume_dir: Path, name: str) -> Path:
    base = Path(name).name
    if base != name or not base.endswith(".md") or base.startswith("."):
        raise ValueError(f"invalid resume file name: {name}")
    return resume_dir / base


def list_files(resume_dir: Path) -> list[dict[str, Any]]:
    if not resume_dir.is_dir():
        return []
    return [
        {"name": f.name, "size": f.stat().st_size,
         "updated_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
        for f in sorted(resume_dir.glob("*.md")) if f.is_file()
    ]


def save(resume_dir: Path, name: str, content: str) -> None:
    path = _path(resume_dir, name)
    data = content.encode()
    if len(data) > MAX_BYTES:
        raise ValueError(f"resume file too large: {len(data)} bytes")
    resume_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete(resume_dir: Path, name: str) -> bool:
    """파일이 없으면 False"""
    path = _path(resume_dir, name)
    if not path.is_file():
        return False
    path.unlink()
    return True
