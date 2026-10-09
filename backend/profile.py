import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from llm import ClaudeAuthError, ask_json

ROOT = Path(__file__).parent.parent
RESUME_FILES = [ROOT / "resume" / "resume.md", ROOT / "resume" / "career_portfolio.md"]
OUT = Path(__file__).parent / "out" / "profile.json"


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


SYSTEM = """당신은 시니어 테크 리크루터입니다. 이력서와 경력기술서에서 지원자의 프로필을 구조화합니다.
규칙:
- 이력서에 근거가 있는 내용만 적습니다. 추측으로 기술이나 경험을 추가하지 않습니다.
- core_skills: 실무에서 주력으로 깊게 쓴 기술. familiar_skills: 써봤지만 주력은 아닌 기술. weak_or_learning: 경험이 적다고 명시된 기술.
- domains: 업무 도메인 (예: 매치메이킹, 결제 이상거래 탐지).
- preferences: 이력서에 명시된 희망 근무지/비자/도메인/역할. 없으면 빈 리스트 또는 null.
- dealbreakers: 지원자에게 맞지 않을 조건 (예: 프론트엔드 전담, 주니어 포지션). 이력서에서 합리적으로 추론 가능한 것만.
- summary: 3문장 이내 한국어 요약."""


def resume_hash() -> str:
    h = hashlib.sha256()
    for f in RESUME_FILES:
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def load_cached() -> Profile | None:
    if not OUT.exists():
        return None
    data = json.loads(OUT.read_text())
    if data.get("hash") != resume_hash():
        return None
    return Profile.model_validate(data["profile"])


async def extract() -> tuple[Profile, float, float]:
    docs = "\n\n".join(f"<document name=\"{f.name}\">\n{f.read_text()}\n</document>" for f in RESUME_FILES)
    prompt = f"다음 문서에서 지원자 프로필을 추출하세요.\n\n{docs}"
    started = time.monotonic()
    res = await ask_json(prompt, Profile.model_json_schema(), system_prompt=SYSTEM)
    profile = Profile.model_validate(res.data)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"hash": resume_hash(), "profile": profile.model_dump()}, ensure_ascii=False, indent=1))
    return profile, time.monotonic() - started, res.cost_usd


async def get_profile() -> Profile:
    cached = load_cached()
    if cached:
        return cached
    profile, _, _ = await extract()
    return profile


async def main() -> int:
    if (cached := load_cached()) and "--force" not in sys.argv:
        print(f"cache hit ({OUT})")
        print(json.dumps(cached.model_dump(), ensure_ascii=False, indent=1))
        return 0
    try:
        profile, elapsed, cost = await extract()
    except ClaudeAuthError as e:
        print(f"auth error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=1))
    print(f"\nextracted in {elapsed:.1f}s, ${cost:.3f} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
