import json

from pydantic import BaseModel

from .llm import LLMError, LLMResult, ask_json
from .profile import Profile

FEEDBACK_MAX_ITEMS = 5


class Feedback(BaseModel):
    items: list[str]  # 개수는 스키마로 강제하지 않는다. generate가 자른다


SYSTEM = """당신은 시니어 테크 리크루터입니다. 지원자 프로필과 채용 공고 하나를 보고, 이 공고에 지원하기 위해 이력서에서 보강하거나 강조할 점을 제안합니다.

입력:
- profile: 지원자 프로필
- 공고 본문, gaps(공고 대비 지원자에게 부족한 점). requirements·preferred·summary는 보조 자료입니다.

규칙:
- gaps는 부족한 점이고, 피드백은 그 부족함을 이력서에서 어떻게 메우거나 드러낼지입니다. gaps를 그대로 반복하지 않습니다.
- 프로필에 근거한 구체적인 경험·성과를 가리킵니다. 어떤 경험을 어떤 표현으로 앞에 내세울지, 어떤 수치·맥락을 보탤지 씁니다.
- 이력서에 없는 경험을 지어내라고 하지 않습니다. 정말 없는 역량이면 인접한 실제 경험을 어떻게 연결해 보여줄지 제안합니다.
- "커뮤니케이션 능력을 강조하세요" 같은 일반론은 쓰지 않습니다. 이 공고와 이 지원자에만 해당하는 내용만 씁니다.

출력: items에 3~5개. 각 항목은 "항목: 설명" 형식의 한국어 한 줄입니다."""


def render(posting: dict) -> str:
    """본문은 DESC_LIMIT 없이 전부. 본문이 없는 기존 판정은 summary·requirements·preferred가 대신한다"""
    lines = [f"회사: {posting.get('company')}", f"제목: {posting.get('title')}"]
    if posting.get("description"):
        lines.append(f"본문:\n{posting['description']}")
    if posting.get("summary"):
        lines.append(f"요약: {posting['summary']}")
    for key, label in (("requirements", "자격요건"), ("preferred", "우대사항")):
        if posting.get(key):
            lines.append(f"{label} (판정 시 충족 여부):\n" + "\n".join(
                f"- {r['text']} [{r.get('fit') or '?'}]" if isinstance(r, dict) else f"- {r}" for r in posting[key]))
    lines.append("gaps:\n" + "\n".join(f"- {g}" for g in posting.get("gaps") or []))
    return "<posting>\n" + "\n".join(lines) + "\n</posting>"


async def generate(profile: Profile, posting: dict) -> tuple[list[str], LLMResult]:
    prompt = (f"<profile>\n{json.dumps(profile.model_dump(), ensure_ascii=False)}\n</profile>\n\n"
              f"{render(posting)}")
    res = await ask_json(prompt, Feedback.model_json_schema(), system_prompt=SYSTEM)
    items = [s.strip() for s in Feedback.model_validate(res.data).items if s.strip()][:FEEDBACK_MAX_ITEMS]
    if not items:
        raise LLMError("empty feedback")
    return items, res
