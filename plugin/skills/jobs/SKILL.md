---
name: jobs
description: gethired CLI로 내 이력서에 매칭된 채용 공고를 읽어 요약한다. "나한테 맞는 공고 있어?", "요즘 새 공고 뭐 있어?", "이직할 만한 포지션 찾아줘", "이력서랑 맞는 채용 보여줘", "job postings that fit my resume", "any new jobs for me?", "find matching positions" 처럼 구직·채용 공고·이직·이력서 매칭을 물을 때 사용.
---

# gethired jobs

gethired가 수집·판정해 둔 공고를 읽어 요약한다. **읽기 전용**: 아래 세 명령만 실행한다.

```bash
uvx --from "gethired>=0.2,<0.3" gethired status --json
uvx --from "gethired>=0.2,<0.3" gethired postings --json [--min-level good] [--company <c>...] [--since 24h|7d] [--limit N] [--full]
uvx --from "gethired>=0.2,<0.3" gethired companies --json
```

`scrape`·`resume`·`provider`·`interest`는 실행하지 않는다. 사용자에게 명령을 안내만 한다.

## 출력
stdout은 JSON만. exit 0이면 결과, 아니면 `{code, message, login_command?, job?}`.

- `status` → `{resume_count, provider, chosen, interests: [...], last_success: {company: run}, stale, job_running}`
  - run = `{id, company, started_at, finished_at, status, error, fetched_count}`. 관심회사가 0이면 `stale`은 true
- `postings` → `[{id, company, title, fit_level, score, fit_reason, apply_url, deadline, scraped_at}]` (`--full`이면 `summary`(공고 요약), `gaps` 추가). 숨김 제외·관심회사만·score 내림차순. `fit_level`은 `strong` > `good` > `stretch`
- `companies` → `[{company, display_name, careers_url, last_run: run | null, interested}]`. DB가 없어도(온보딩 전) 목록은 나온다
- 오류 `code`
  - `not_onboarded` (exit 1): DB 없음. 온보딩 안내로
  - `job_running` (exit 1): 다른 곳에서 스크래핑 중. 끝나면 다시 읽는다
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

## sandbox
sandbox에서 `uvx`가 막히면(uv 캐시 쓰기·PyPI 접근 실패) 사용자에게 "gethired 조회를 위해 sandbox 밖에서 실행해도 될까요?"라고 승인을 받아 sandbox 밖에서 실행한다. 반복 승인을 줄이려면 설정의 permissions allow에 `Bash(uvx --from "gethired>=0.2,<0.3" gethired *)`를 추가하거나 sandbox 쓰기 경로에 uv 캐시(`~/.cache/uv`)를 넣으라고 안내한다.
