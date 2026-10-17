import hashlib
from pathlib import Path

from pydantic import BaseModel

from . import resume
from .config import RESUME_DIR
from .llm import ask_json
from .repository import Repository, now_iso


class Preferences(BaseModel):
    locations: list[str]
    visa_or_work_authorization: str | None
    target_domains: list[str]
    target_roles: list[str]


class Profile(BaseModel):
    name: str | None
    seniority: str
    years_experience: float
    core_skills: list[str]
    familiar_skills: list[str]
    weak_or_learning: list[str]
    domains: list[str]
    notable_achievements: list[str]
    preferences: Preferences
    dealbreakers: list[str]
    summary: str


SYSTEM = """당신은 시니어 테크 리크루터입니다. 지원자가 제공한 문서(이력서, 경력기술서, 희망 조건 등)에서 지원자의 프로필을 구조화합니다.
규칙:
- 이력서에 근거가 있는 내용만 적습니다. 추측으로 기술이나 경험을 추가하지 않습니다.
- core_skills: 실무에서 주력으로 깊게 쓴 기술. familiar_skills: 써봤지만 주력은 아닌 기술. weak_or_learning: 경험이 적다고 명시된 기술.
- domains: 업무 도메인 (예: 매치메이킹, 결제 이상거래 탐지).
- preferences: 문서에 명시된 희망 근무지/비자/도메인/역할. 희망 조건을 다룬 문서가 있으면 그 내용을 우선 반영. 없으면 빈 리스트 또는 null.
- dealbreakers: 지원자에게 맞지 않을 조건 (예: 프론트엔드 전담, 주니어 포지션). 문서에서 합리적으로 추론 가능한 것만.
- summary: 3문장 이내 한국어 요약."""


def source_files() -> list[Path]:
    if not RESUME_DIR.is_dir():
        return []
    return sorted(f for f in RESUME_DIR.iterdir()
                  if f.is_file() and f.suffix in resume.EXTENSIONS and not f.name.startswith("."))


def source_hash(files: list[Path] | None = None) -> str:
    h = hashlib.sha256()
    for f in files or source_files():
        h.update(f.name.encode())
        with f.open("rb") as fp:
            while chunk := fp.read(1024 * 1024):
                h.update(chunk)
    return h.hexdigest()[:16]


async def extract(files: list[Path]) -> Profile:
    docs = "\n\n".join(f'<document name="{f.name}">\n{resume.extract_text(f)}\n</document>' for f in files)
    res = await ask_json(f"다음 문서에서 지원자 프로필을 추출하세요.\n\n{docs}",
                         Profile.model_json_schema(), system_prompt=SYSTEM)
    return Profile.model_validate(res.data)


async def get_profile(repo: Repository, force: bool = False) -> Profile:
    files = source_files()
    if not files:
        raise FileNotFoundError(f"no *.md / *.pdf files in {RESUME_DIR}")
    h = source_hash(files)
    if not force and (cached := repo.get_profile_cache(h)):
        return Profile.model_validate(cached)
    profile = await extract(files)
    repo.set_profile_cache(h, profile.model_dump(), now_iso())
    return profile
