import hashlib
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel

from . import resume
from .config import RESUME_DIR
from .llm import ask_json
from .repository import Repository, now_iso

Role = Literal[
    "backend", "frontend", "fullstack", "ios", "android", "cross-platform-mobile",
    "data-engineering", "data-science", "ml-engineering", "ml-research",
    "infra-sre", "security-engineering", "qa", "embedded", "game-client",
]
ROLES: tuple[str, ...] = get_args(Role)


class Preferences(BaseModel):
    locations: list[str]
    visa_or_work_authorization: str | None
    target_domains: list[str]
    target_roles: list[str]


class Profile(BaseModel):
    name: str | None
    seniority: str
    roles: list[Role] = []
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
- roles: 경력에서 추론한 주력 직군 1~3개. 어휘는 스키마의 enum 그대로. 희망이 아니라 지금까지 해온 일 기준이며, 조금 만져본 분야는 넣지 않습니다. 판단이 서지 않으면 빈 리스트.
- core_skills: 실무에서 주력으로 깊게 쓴 기술. familiar_skills: 써봤지만 주력은 아닌 기술. weak_or_learning: 경험이 적다고 명시된 기술.
- domains: 업무 도메인 (예: 매치메이킹, 결제 이상거래 탐지).
- preferences: 문서에 명시된 희망 근무지/비자/도메인/역할. 희망 조건을 다룬 문서가 있으면 그 내용을 우선 반영. 없으면 빈 리스트 또는 null.
- dealbreakers: 지원자에게 맞지 않을 조건 (예: 주니어 포지션, 특정 근무지). 문서에서 합리적으로 추론 가능한 것만.
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
    cached = None if force else repo.get_profile_cache(h)
    if cached and "roles" in cached:  # roles 없는 캐시는 이전 스키마 → 재추출
        return Profile.model_validate(cached)
    profile = await extract(files)
    repo.set_profile_cache(h, profile.model_dump(), now_iso())
    return profile
