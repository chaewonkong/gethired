---
name: jobs
description: gethired CLI로 내 이력서에 매칭된 채용 공고를 읽어 요약한다. "나한테 맞는 공고 있어?", "요즘 새 공고 뭐 있어?", "이직할 만한 포지션 찾아줘", "이력서랑 맞는 채용 보여줘", "job postings that fit my resume", "any new jobs for me?", "find matching positions" 처럼 구직·채용 공고·이직·이력서 매칭을 물을 때 사용.
---

# gethired jobs

gethired가 수집·판정해 둔 공고를 읽어 요약한다. **읽기 전용**: 아래 네 명령만 실행한다.

```bash
uvx --from gethired~=0.4.0 gethired status --json
uvx --from gethired~=0.4.0 gethired postings --json [--min-level good] [--company <c>...] [--since 24h|7d] [--limit N] [--full]
uvx --from gethired~=0.4.0 gethired companies --json
uvx --from gethired~=0.4.0 gethired posting <id> --json [--body]
```

`scrape`·`resume`·`provider`·`interest`는 실행하지 않는다. 사용자에게 명령을 안내만 한다. 이력서 피드백 생성은 UI 상세 화면의 "피드백 생성" 버튼으로만 된다 (CLI는 캐시된 피드백만 읽음).

## 출력
stdout은 JSON만. exit 0이면 결과, 아니면 `{code, message, login_command?, job?}`.

- `status` → `{resume_count, provider, chosen, interests: [...], last_success: {company: run}, stale, job_running}`
  - run = `{id, company, started_at, finished_at, status, error, fetched_count}`. 관심회사가 0이면 `stale`은 true
- `postings` → `[{id, company, title, fit_level, score, fit_reason, apply_url, deadline, scraped_at}]` (`--full`이면 `summary`(공고 요약), `gaps`, `breakdown` 추가). 숨김 제외·관심회사만·score 내림차순. `fit_level`은 `strong` > `good` > `stretch`
- `companies` → `[{company, display_name, careers_url, last_run: run | null, interested}]`. DB가 없어도(온보딩 전) 목록은 나온다
- `posting <id>` → `{id, company, title, fit_level, score, fit_reason, apply_url, deadline, scraped_at, summary, gaps, tech_stack, requirements, preferred, breakdown, feedback}` (`--body`면 `description`(공고 본문) 추가)
  - `requirements`(자격요건)·`preferred`(우대사항): 한 줄씩 문자열 목록
  - `breakdown` = `{skills, domain, seniority, preferred}` (만점 35/35/20/10, 합계 = `score`). 축은 핵심 기술·도메인·연차·우대사항
  - `feedback` = `{items, created_at, current} | null`: UI에서 생성해 캐시된 이력서 피드백만. `current: false`면 이전 이력서 기준
  - 이전 버전에서 판정한 공고는 `requirements`·`preferred`·`breakdown`이 null (다음 스크래핑 때 재판정). `postings --full`의 `breakdown`도 같다
- 오류 `code`
  - `not_onboarded` (exit 1): DB 없음. 온보딩 안내로
  - `job_running` (exit 1): 다른 곳에서 스크래핑 중. 끝나면 다시 읽는다
  - `not_found` (exit 1): `posting <id>`의 공고가 없거나 삭제됨
  - 그 외는 `message`를 그대로 전한다

## 절차
1. `status --json`
2. 온보딩 부족이면 필요한 명령만 안내하고 멈춘다 (`not_onboarded`면 전부)
   - `resume_count == 0` → `uvx gethired resume add <이력서.md|.pdf>`
   - `chosen == false` → `uvx gethired provider claude` (또는 `codex`)
   - `interests == []` → `companies --json`으로 목록을 보여주고 `uvx gethired interest add <company...>`
   - 브라우저가 편하면 `uvx gethired`로 UI에서 해도 된다
3. `stale`(관심회사 중 마지막 성공 실행이 24h 초과 또는 없음)이거나 `job_running`이면
   - 터미널에서 `uvx gethired scrape` 실행을 안내한다 (직접 실행하지 않는다. 수 분 걸리고 provider CLI를 중첩 호출하게 됨)
   - `job_running`이면 "이미 실행 중, 끝나면 알려 달라"
   - 기존 공고가 있으면 오래된 데이터라고 밝히고 4로 진행해도 된다
   - 사용자가 완료를 알리면 1부터 다시 읽는다
4. `postings --json` (질문에 맞게 `--min-level`·`--company`·`--since` 사용. "새 공고"면 `--since 24h` 또는 `7d`)
5. 요약: 등급순으로 `등급 · 회사 · 제목 — 이유(fit_reason 한 줄) · 링크(apply_url)`. 마감(`deadline`)이 가까우면 표시. 많으면 strong·good 위주로 자르고 남은 건수를 말한다. 0건이면 그렇게 말하고 `--min-level` 완화나 scrape를 제안
6. 특정 공고를 더 자세히 물으면 `posting <id> --json`으로 요건·우대사항·축별 점수(`breakdown`, 예: 기술 30/35)를 보여준다. 피드백이 있으면 함께 (`current: false`면 이전 이력서 기준이라고 밝힘), 없으면 UI 상세의 "피드백 생성"을 안내. `--body`는 사용자가 공고 원문을 물을 때만

## sandbox
sandbox에서 `uvx`가 막혀도(uv 캐시 쓰기·PyPI 접근) 사용자에게 따로 묻지 않는다. 에이전트의 기본 권한 절차대로 재실행하고, 승인은 그 절차에 맡긴다. 승인을 반복해서 물으면 README "에이전트에서 쓰기"의 권한 설정을 안내한다.
