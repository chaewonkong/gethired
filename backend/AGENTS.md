# backend

FastAPI + sqlite. 채용 사이트 스크래핑(httpx) → 이력서 프로필 기반 LLM 판정(Claude Agent SDK 또는 Codex CLI) → 저장·조회 API.
설계 근거는 `../design/specs/`.

## 명령 (backend/에서)
```bash
UV_CACHE_DIR=../.uv-cache uv run pytest        # 단위·API 테스트, 네트워크/LLM 없음
uv run ruff check app tests scripts           # 린트 (규칙: pyproject [tool.ruff.lint], CI ci-backend.yml과 동일)
LIVE=1 uv run pytest tests/test_scrapers_live.py  # 실제 사이트 호출
uv run uvicorn app.main:app --reload --port 8000
uv run gethired [serve] [--port 8000] [--no-open] [--demo]   # 설치형 진입점 (= python -m app)
uv run gethired auth [claude|codex] · reset-db · paths
uv run gethired status|companies|postings|posting|scrape|resume|provider|interest [--json]   # 헤드리스 CLI (아래 "CLI")
uv run python -m app --demo --port 8000       # 데모 모드: 가짜 스크래퍼·판정, 임시 DB·이력서, 네트워크/LLM/CLI 없음
```
sandbox에서는 홈 uv 캐시에 쓸 수 없으므로 `UV_CACHE_DIR=../.uv-cache`를 붙인다.
데이터 경로 기본값은 platformdirs 사용자 디렉토리(`GETHIRED_HOME`). justfile은 `DB_PATH`·`RESUME_DIR`로 저장소 안(`backend/data/app.db`, `resume/`)을 가리킨다. 패키지(`gethired`, hatchling)는 `app/static/`(프론트 빌드)을 휠에 포함한다 (`just build-wheel`).

## 흐름
`POST /api/scrape` → `JobManager.prepare()`(로그인·대상) → `start()`(락 + job) → 프로필 로드 → 회사별 병렬로
fetch → `mark_seen` / `soft_delete_missing` → 미판정 공고(+ breakdown 없는 기존 공고)만 `judge` → 재판정 exclude는 `delete_postings` → exclude 아닌 것만 `upsert_postings` → `record_judgments`

### 구성
```
  [User]
     |
     v
+----------------------------------------+
| frontend (React)                       |
| tabs: Postings | Bookmarks | Applied   |
|       | Hidden | Companies | Detail    |
+----------------------------------------+
     |  /api/*
     v
+-------------+      +---------------+      +----------------------+
| api.py      |----->| repository.py |----->| sqlite               |
| (FastAPI)   |      +---------------+      | backend/data/app.db  |
+-------------+              ^              +----------------------+
     | POST /api/scrape      | save postings / judgments
     v (background)          |
+-------------+              |
| jobs.py     |--------------+
+-------------+
     |
     +--> scrapers/   -- httpx ---------> career sites (23)
     |
     +--> profile.py  -- read ----------> resume/*.md, *.pdf (pdf는 pypdf로 텍스트 추출)
     |                -- cache ---------> repository.py (profile_cache, key = resume hash)
     |                -- extract -------> LLM (provider CLI 로그인 세션)
     |
     +--> matcher.py  -- judge 10/batch -> LLM
```
- 스크래핑은 httpx로 짠 결정적 코드이고, LLM은 프로필 추출과 공고 판정에만 쓴다
- LLM은 API key 없이 provider(Claude Code / Codex) CLI의 로컬 로그인 세션으로 호출한다. provider는 `settings` 테이블에 저장되고 UI에서 고른다

### 스크래핑 한 번의 흐름
```
[스크래핑 하기] 클릭
 |
 +-> POST /api/scrape
 |     job 생성 후 job_id 즉시 반환. frontend는 끝날 때까지 1.5초마다 GET /api/scrape/{job_id}
 |
 +-> 1. profile
 |     resume/*.{md,pdf} 해시로 캐시 조회 -> 없거나 바뀌었으면 LLM으로 추출
 |
 +-> 2. per company (parallel)
 |     회사별로 동시에 실행, 한 회사가 실패해도 나머지는 계속
 |     a. fetch ............. 채용 사이트에서 공고 수집 (0건이면 실패 처리)
 |     b. sync .............. 다시 나온 공고 복구, 사라진 공고 soft delete
 |     c. filter ............ 이미 판정한 공고 제외 (저장 공고 중 breakdown 없는 것은 재판정 대상)
 |     d. judge ............. 신규·재판정 공고만 LLM으로 10건씩 판정 (본문 6000자까지)
 |     e. save .............. strong/good/stretch는 postings에 저장 (본문·요건·우대·breakdown 포함)
 |                            exclude는 judgments에만 기록 (재판정 방지)
 |                            재판정에서 exclude가 된 기존 공고는 북마크·숨김·피드백과 함께 hard delete
 |
 +-> 3. done
       frontend가 GET /api/postings로 목록 갱신 (등급, 북마크 여부 포함)
```
- 세션이 만료되면 job이 `auth_required`로 끝나고, 다음 실행에서 판정 못 한 공고만 다시 판정한다
- 북마크는 공고와 JOIN으로 묶여 있어서, 공고가 삭제되면 같이 숨겨지고 공고가 다시 나타나면 같이 돌아온다

## 모듈
| 파일 | 역할 |
|---|---|
| `app/config.py` | 경로(`HOME`=platformdirs 또는 `GETHIRED_HOME`, `DB_PATH`=`HOME/app.db`, `RESUME_DIR`=`HOME/resume`, `FRONTEND_DIST`=`app/static`), 매칭 배치 크기(`MATCH_BATCH_SIZE` 10)·동시성. env override: `GETHIRED_HOME`, `DB_PATH`, `RESUME_DIR`, `LLM_PROVIDER`, `LLM_TIMEOUT_S`, `CLAUDE_MODEL`, `CODEX_BIN`, `CODEX_MODEL` |
| `app/scrapers/base.py` | `RawPosting`(정규화된 공고), `Scraper` ABC, `REGISTRY`(서브클래스 정의 시 자동 등록), `html_to_text`, `parse_date` |
| `app/scrapers/<company>.py` | 회사별 `fetch()`. 엔지니어링 직군 1차 필터는 여기서. 원본 분류는 `category`에 보존 |
| `app/scrapers/greenhouse.py` | Greenhouse 계열 공통 베이스 (쿠팡·당근·토스·몰로코·크래프톤). `content`는 entity-escaped HTML이라 `description`에서 unescape 후 `html_to_text` |
| `app/scrapers/ninehire.py` | Ninehire 계열 공통 베이스 (에이블리). 공개 JSON API(목록 `countPerPage=100` 페이징, 상세 `job-posting`) |
| `app/scrapers/greetinghr.py` | GreetingHR 계열 공통 베이스 (업스테이지·카카오페이·카카오모빌리티·컬리; 오늘의집은 목록이 Gatsby page-data라 상세 파서만 재사용). 공개 API가 없어 목록은 첫 페이지, 본문은 공고 페이지의 `__NEXT_DATA__`에서 꺼낸다 |
| `app/llm.py` | `ask_json()`: structured output 래퍼. `configure(provider)`로 모듈 상태를 두고 claude(Agent SDK) / codex(`codex exec` subprocess) 분기. 인증 실패는 `LLMAuthError`, 그 외 `LLMError`. codex는 호출 전 `is_logged_in` 선체크(미로그인 exec는 끝나지 않음), strict schema 변환(`to_strict_schema`), `-o` 파일로 결과, `--json`으로 usage·401 감지. runner는 `llm.codex_runner`로 주입 |
| `app/auth.py` | `is_logged_in(provider)`: claude는 `claude auth status` JSON, codex는 `$CODEX_BIN login status` exit code. provider별 single-flight |
| `app/profile.py` | `resume/*.md`·`*.pdf` → `Profile`. 본문은 `resume.extract_text`(문서당 50k자 상한). 파일 이름·내용 해시(1MB 청크)로 `profile_cache`에 캐시. `roles`(직군 enum `ROLES` 15개, 경력 기준)가 없는 캐시는 재추출 |
| `app/resume.py` | `resume/` 파일 목록·저장·삭제·텍스트 추출. 파일명은 basename만, `.md`·`.pdf`만, 크기 제한 없음(임시 dotfile에 스트리밍 후 `os.replace`), 디렉토리 자동 생성, 같은 이름 덮어쓰기. `extract_text`: md는 그대로, pdf는 pypdf, `TEXT_LIMIT`(50k자) 초과는 잘라 `[이하 생략]`. 텍스트 없는 pdf는 저장 취소 + `ValueError`(API 400) |
| `app/matcher.py` | 10건 배치 판정(본문 `DESC_LIMIT` 6000자) → `Match`(fit_level/score/breakdown/gaps/summary/tech_stack/requirements/preferred/fit_reason). requirements·preferred 항목은 `Requirement` = `{text, fit}`(fit은 `FIT_MARKS` met·partial·unmet, 지원자 기준 충족 여부). `Breakdown` = skills·domain·seniority·preferred(만점 `BREAKDOWN_MAX` 35/35/20/10). 범위·개수는 스키마로 강제하지 않고(한 건 실패 = 배치 재시도) `Match.normalize()`가 정리: requirements·preferred 최대 8개·80자 절단, 축 clamp, 합계 ≠ score면 score = 합계, 그 뒤 score 구간으로 fit_level 보정 (score 구간이 fit_level보다 우선). 누락 id는 재시도. 역할 기준은 프로필 `roles`·`ADJACENT`(인접 직군 표, 대칭, SYSTEM에 렌더링)이며 비개발 직군만 exclude |
| `app/repository.py` | sqlite 접근 전부. 테이블: `postings`, `judgments`, `bookmarks`, `hides`, `feedbacks`(PK posting_id·profile_hash, items JSON), `interests`, `scrape_runs`, `profile_cache`, `applications`(spec 0015: PK posting_id, `stage` TEXT(이번엔 NULL), created_at=지원일, updated_at, deleted_at=사용자 해제 전용), `settings`(key/value, `provider`). `postings`는 `description`(본문)·`requirements`·`preferred`·`breakdown`(JSON)을 nullable로 가진다(spec 0014 이전 행은 NULL, `_migrate`가 컬럼 추가). `postings.first_seen_at`은 처음 저장 시각(upsert 충돌·`mark_seen`에도 유지, `scraped_at`은 최근 확인 시각). 기존 DB는 `_migrate()`가 컬럼 추가 후 `scraped_at`으로 채움. `now_iso()`는 `set_fixed_now()`로 고정 가능(데모 모드). `Repository(path, readonly=True)`는 `file:...?mode=ro`, 스키마 생성 생략, 파일 없으면 `FileNotFoundError`. `list_postings(..., include_hidden=True, interests_only=False, since=None, include_applied=True)`(기본값 = 기존 동작, `since`는 `first_seen_at` 기준. 응답 크기 때문에 `_row`가 `description`을 뺀다), `get_posting(id)`(상세, description 포함, 삭제는 None·숨김은 반환. 단 지원완료 공고는 삭제돼도 반환), 행에는 `application: {applied_at, stage} | None`·`deleted_at` 포함. 삭제 조건은 `_alive()` = `p.deleted_at IS NULL OR a.posting_id IS NOT NULL`(지원완료는 이력이라 soft delete돼도 목록·상세에 남는다). `set_application(id, now)`(활성 공고 없으면 None, 이미 지원완료면 created_at 유지, 해제 후 재지원은 갱신)·`clear_application(id, now)`(공고 행 없으면 False, 마감이어도 True)·`get_application(id)`. readonly 옛 DB에 `applications`가 없으면(`_has_applications`) JOIN 없는 SELECT로 폴백하고 `application`은 None·삭제 조건은 기존대로, `delete_postings(company, ids)`(hard delete, bookmarks·hides·feedbacks·applications 먼저), `judged_ids`(stored인데 breakdown NULL이면 제외 → 재판정. exclude는 그대로 judged), `set_feedback`·`feedback_for(id, hash)`(현재 해시면 `current: true`, 없으면 최근 이전 것 `current: false`, 테이블 없으면 None). requirements·preferred에 문자열 항목이 있으면(0.5.0 개발 중 저장) `_row`가 `{text, fit: null}`로 정규화. readonly 옛 DB(컬럼·`feedbacks` 없음)도 `_row`가 키 없이 통과시키고 소비자는 `.get()`으로 읽는다. SELECT는 `p.*` 유지(명시 컬럼은 옛 DB에서 실패), `last_success_runs()`(회사별 마지막 `done` run), `stale(companies, now, hours=24)` |
| `app/jobs.py` | 스크래핑 job 실행·상태(`Job`, `CompanyState`). `prepare(companies)`: 로그인 선체크(`LoginRequired`: provider·login_command·message) + 대상 계산(`NoTargets`: 관심회사 0·unknown company). `start(targets)`: 동기로 락 획득 후 job 생성·task 시작(UI). `run(targets)`: `start` 후 완료 대기(CLI). 락은 `filelock`으로 `DB_PATH.with_suffix(".lock")`(`lock_path`로 주입), 보유 중이면 `JobRunning`. 같은 인스턴스 재진입은 `FileLock`이 허용하므로 `is_locked`를 먼저 본다. `is_locked()`: 자기 프로세스는 `self._lock.is_locked`, 다른 프로세스는 락 파일을 `O_RDONLY`로 열어 `flock(LOCK_SH\|LOCK_NB)` 실패 여부(파일을 만들거나 쓰지 않음. 파일 없으면 False. Windows는 FileLock try-acquire 폴백, 미검증). job 시작 시 settings의 provider로 `llm.configure()`, job 전체가 그 provider로 고정(`Job.provider`). 회사 단위 실패 격리. 판정 뒤 exclude가 된 공고는 `delete_postings`(재판정 대상이었던 기존 행만 실제로 지워짐, `excluded` 건수에 포함). 세션 만료 시 `auth_required`, 프로필 추출 실패는 `Job.error`. 취소(`CancelledError`)면 열린 run을 `failed`/`interrupted`로 마감하고 `job.status = "interrupted"`, `finally`에서 락 해제 |
| `app/api.py` | `create_app(repo, jobs, logged_in: (provider) -> bool, resume_dir, feedback_fn, profile_loader, profile_hash)`(뒤 셋은 테스트·데모 주입용, 기본값 `feedback.generate`·`get_profile`·`source_hash`): `/api/{settings/provider, auth/status, companies, companies/{c}/interest, interests, scrape, scrape/{id}, postings, postings/{id}, postings/{id}/feedback, postings/{id}/bookmark, postings/{id}/hide, postings/{id}/application, resume, resume/{name}}`. 목록은 `breakdown` 포함·`description` 제외, `application`·`deleted_at` 포함(마감된 지원완료 공고도 내려간다). `PUT postings/{id}/application`: body 없음, 200 `{posting_id, application: {applied_at, stage}}`(멱등), 없음·마감 404. `DELETE`: 마감 여부 무관 200 `{posting_id, application: null}`, 공고 행 없으면 404. `GET postings/{id}`: 상세 + `description`·`requirements`·`preferred`·`breakdown`·`feedback`(캐시, `profile_hash()` 기준), 없음·삭제 404(지원완료 공고는 삭제돼도 200). `POST .../feedback`도 같은 조건이라 마감된 지원완료 공고에 허용(spec 0015 예외). `POST postings/{id}/feedback`: 404 → `is_locked()` 409 `job_running` → 캐시 적중이면 LLM 없이 200 → 로그인 선체크 401 `login_required` → `profile_loader`(이력서 없음 400 `no_resume`) → 생성(`LLMError` 502 `llm_error`) → 저장. legacy 공고도 허용. `GET settings/provider`는 DB만(`{provider, chosen}`), `auth/status`는 CLI 실행. `PUT settings/provider`는 `is_locked()`면 409, 저장 후 auth status 반환. `POST scrape`: 자기 프로세스 job이 running이면 그 job 202 → `prepare()` → `LoginRequired` 401 `{code: "login_required", provider, message, login_command}` / `NoTargets` 400 → `start()` → `JobRunning` 409 `{code: "job_running", message}` |
| `app/feedback.py` | `generate(profile, posting) -> (items, LLMResult)`: 공고 기준 이력서 보강·강조점 3~5개("항목: 설명"). 입력은 프로필 + 본문(한도 없음)·gaps, 보조로 requirements·preferred·summary. 본문 없는 legacy는 summary·requirements로 대체. 5개 초과는 절단, 0개면 `LLMError`. gaps(부족한 점)와 역할을 나누고 없는 경험을 지어내지 않게 지시 |
| `app/static.py` | `SPAStaticFiles(StaticFiles)`: 404이고 마지막 세그먼트에 `.`이 없으면 `index.html`로 응답(`/postings/1` 직접 진입). `api/` 접두는 404 유지 |
| `app/main.py` | 앱 조립 + `app/static` 정적 서빙(`SPAStaticFiles`, `html=True`). `ANTHROPIC_API_KEY`·`OPENAI_API_KEY` 제거 |
| `app/__main__.py` | 콘솔 진입점 `gethired` → `cli.main` |
| `app/cli.py` | argparse 서브커맨드 전부(아래 "CLI"). `serve`(기본, 브라우저 오픈, `--no-open`·`--demo`, `uvicorn.run`에 app 객체)·`auth`·`reset-db`·`paths` + 헤드리스 명령. `_emit`(stdout JSON / 사람용 표)·`_fail(code, message, exit_code, login_command=None)`. 키 집합은 `POSTING_FIELDS`·`FULL_FIELDS`·`DETAIL_FIELDS`(`application` 포함). `postings`는 `include_applied=False`로 지원완료 제외(목록 키에 `application` 없음). 사람용 `posting`은 `지원완료: <applied_at>`(마감이면 `(마감됨)`) 한 줄. 사람용 `posting` 출력은 요건 항목 앞에 `FIT_MARK`(V·△·X). `posting`의 피드백 캐시 키는 `_resume_hash(env)`(= 서버 `source_hash`, 파일 0개면 `""`, 데모 모드면 `"demo"`로 데모 앱의 `profile_hash`와 맞춤). 진입 시 `ANTHROPIC_API_KEY`·`OPENAI_API_KEY` 제거. 읽기 명령은 `Repository(readonly=True)`, DB 없으면 `status`·`postings`·`posting`은 `not_onboarded`(`companies`·`provider` 조회는 기본값) |
| `app/demo.py` | 데모 모드(`python -m app --demo`, README GIF 녹화용). 토스·당근·카카오·네이버 가짜 스크래퍼(`register=False`, 공고 8건) + 고정 프로필·판정(strong 2 · good 3 · stretch 3), `logged_in` 항상 True, `set_fixed_now("2026-10-18T09:00:00+09:00")`. `make_jobs(repo, lock_path)`·`demo_paths()`를 `make_app`과 CLI(`GETHIRED_DEMO=1`)가 같이 쓴다. `make_app`은 `DB_PATH`/`RESUME_DIR` env가 없으면 임시 디렉토리, CLI는 exit 1. `DEMO_JUDGE_DELAY_S`(기본 0.7)로 진행 상태 노출. `GETHIRED_DEMO=1`일 때만 모듈 수준 `app` 생성 |
| `scripts/` | 디버그용, 결과는 `out/`에 파일로. `run_scrape.py`(`just scrape`): 스크래퍼만 실행 + 건수·중복·본문 확보율 경고. `match.py`(`just match`): `out/*.json`을 판정해 `out/fit.md` 생성, `--planted`로 정답 공고 검증, `--provider`로 하네스 선택. DB는 `profile_cache`만 사용. `resume_text.py`(`just resume-text`): 이력서 텍스트 추출 결과를 `out/resume_text/`에 저장. `auth_check.py`: Agent SDK 세션 인증 확인 (PoC용) |

## CLI
`gethired <command> [--json]`. stdout은 JSON만, 진행·로그는 stderr. 필드 이름은 API와 같다. 키 집합은 `tests/test_cli.py`가 고정하고 `plugin/skills/jobs/SKILL.md`가 그대로 쓴다

| 명령 | JSON |
|---|---|
| `status` | `{resume_count, provider, chosen, interests, last_success: {company: run}, stale, job_running}`. run = `{id, company, started_at, finished_at, status, error, fetched_count}`. 관심회사 0이면 `stale` true |
| `postings [--min-level] [--company ...] [--since 24h\|7d] [--limit N] [--full]` | `[{id, company, title, fit_level, score, fit_reason, apply_url, deadline, scraped_at}]`, `--full`이면 `+summary, gaps, breakdown`(본문은 `posting --body`로만). 숨김·지원완료 제외·관심회사만 |
| `posting <id> [--body]` | `{id, company, title, fit_level, score, fit_reason, apply_url, deadline, scraped_at, summary, gaps, tech_stack, requirements, preferred, breakdown, feedback, application}`, `--body`면 `+description`. `feedback` = `{items, created_at, current}\|null`(캐시만, 생성하지 않음. 해시는 `source_hash()`). `application` = `{applied_at, stage}\|null`(지원완료 공고는 마감돼도 반환). legacy 컬럼은 null. 없음, 또는 지원완료가 아닌 삭제 공고는 `not_found` |
| `companies` | `/api/companies`와 동일 `[{company, display_name, careers_url, last_run: run\|null, interested}]`. DB 없으면 관심·실행 없이 목록만 |
| `scrape [company...]` | `{job_id, status, provider, started_at, finished_at, cost_usd, error, companies: {c: {status, fetched, new, stored, excluded, deleted, error}}, failed: [{company, error}]}`. `prepare()` → `run()`, 진행은 stderr에 바뀐 회사만 1초 폴링 |
| `resume add\|list\|rm` · `provider [name]` · `interest add\|rm` | 온보딩. `provider <name>`은 락 보유 중이면 `job_running` |
| 오류 | `{code, message, login_command?, job?}` (`job`은 scrape 시작 뒤 실패·중단 시 부분 결과) |

exit: 0 성공(일부 회사 실패는 `failed`) · 1 `all_failed`·`profile_failed`·`no_targets`·`job_running`·`invalid_resume`·`not_onboarded`·`not_found`·`invalid_argument` · 3 `login_required`(선체크 또는 도중 `auth_required`) · 130 `interrupted`(Ctrl+C: `asyncio.run`의 cancel이 `run()`→`_run`→`_run_company`로 전파, 락 해제)

## 규칙
- 스크래핑과 provider 변경은 같은 DB를 쓰는 프로세스끼리 락(`app.lock`)으로 배타. 락 검사(`is_locked`)는 파일을 만들거나 쓰지 않는다 (읽기 명령이 쓰기 불가 디렉토리에서도 동작)
- CLI 읽기 명령은 DB를 `mode=ro`로 열고 스키마를 만들지 않는다
- LLM은 선택한 provider CLI(Claude Code / Codex)의 로컬 로그인 세션으로만 호출한다. API key를 쓰지 않는다
- Claude Code sandbox 안에서는 실제 `codex exec`가 실패한다(`~/.codex` 쓰기 불가). codex 경로는 runner fake로 테스트하고, 라이브 확인은 sandbox 밖에서
- 스크래핑은 결정적 코드(httpx)로. LLM은 프로필 추출과 매칭에만 쓴다
- 스크래퍼가 0건을 반환하면 실패로 처리한다 (soft delete 오작동 방지)
- 삭제는 soft delete(`deleted_at`). 공고가 다시 나타나면 복구된다. 예외: 재판정에서 exclude가 된 공고는 hard delete (`mark_seen`이 soft delete를 되살리므로)
- `bookmarks.deleted_at`·`hides.deleted_at`은 사용자 해제 전용. 공고 삭제 여부는 `postings`와 JOIN으로 판단
- `applications.deleted_at`도 사용자 해제 전용. 북마크·숨김과 달리 지원완료는 이력이라 공고 soft delete 후에도 목록·상세에 남는다(`_alive()`). 마감 공고는 새로 지원완료·북마크·숨김할 수 없고(404) 해제만 된다. hard delete(`delete_postings`)는 `applications`도 함께 지운다
- exclude 판정은 `postings`에 저장하지 않고 `judgments`에만 기록한다 (재판정 방지). 단 breakdown 없는 기존 저장 공고는 1회 재판정하고, 결과가 exclude면 행을 북마크·숨김·피드백과 함께 지운다(북마크 예외 없음)
- `POST /api/scrape`를 파라미터 없이 부르면 관심회사(`interests`)만 스크래핑한다. 관심회사가 없으면 400
- 관심회사 해제는 `interests` row만 지운다. 공고·판정은 남기고, 관심회사 기준 숨김은 프론트에서 한다
- Agent SDK `query()` 제너레이터 안에서 raise하지 않는다 (aclose 충돌). 플래그를 세우고 루프 밖에서 raise
- 스키마 변경은 `CREATE TABLE IF NOT EXISTS`로 기존 `data/app.db`와 호환되게. 컬럼 추가는 마이그레이션 필요
- 데모 모드(`demo.py`)는 실제 경로(`data/`, `resume/`)·CLI·LLM·네트워크를 쓰지 않는다. 데모 텍스트는 전부 가상. `REGISTRY`에 등록하지 않는다

## 새 회사 추가
1. `app/scrapers/<company>.py`에 `Scraper` 구현 (Greenhouse면 `GreenhouseScraper` 상속)
2. `app/scrapers/__init__.py` import 목록에 추가 (import 시 등록됨)
3. `fixtures/`에 응답 샘플 저장 + `tests/test_parsers*.py`에 파싱 테스트, `test_registry_has_all_companies` 갱신
4. 새 도메인은 `.claude/settings.json`의 sandbox `allowedDomains`에 추가

소스별 주의:
- Greenhouse / Lever(하이퍼커넥트, Match Group 보드) / Ashby(42dot)는 공개 JSON API. 하이퍼커넥트는 서울 포지션 전부(Match Group 소속 포함)를 가져오고 소속은 `category`로 구분
- 두나무는 API가 없어 `RSC: 1` 헤더로 받은 Next.js 페이로드를 파싱한다. 본문 청크 길이는 UTF-8 바이트 수이고 청크 뒤에 개행이 없어 bytes로 순차 파싱한다. 빌드가 바뀌면 fixture 테스트가 먼저 깨진다
- 기아는 현대차와 같은 플랫폼(`career.kia.com`, `X-HKMC-TOKEN: null` 헤더 필요)이지만 엔지니어링 공고가 없어 보류

## 테스트
- `tests/test_parsers*.py`: `fixtures/`의 저장된 응답으로 파서 검증
- `tests/test_repository.py`: in-memory sqlite. 옛 스키마 마이그레이션·readonly 옛 DB, `judged_ids` 재판정 규칙, `delete_postings`, `feedback_for`, 지원완료(멱등·재지원·마감 유지·readonly 폴백)
- `tests/test_resume.py` · `tests/test_profile.py`: 텍스트 추출(`fixtures/resume_sample.pdf`, `resume_blank.pdf`는 합성 PDF), 절단, 프로필 문서 구성·해시
- `tests/test_llm.py` · `tests/test_llm_codex.py` · `tests/test_auth.py`: provider 분기, strict 변환, codex 출력 파싱(`fixtures/codex_*.jsonl`, 실측 출력), 인증 판별, single-flight. 실제 CLI 실행 없음. `conftest.py`가 매 테스트 후 `configure("claude")`
- `tests/test_api.py`: `FakeScraper` + fake judge/profile로 job·API 전체 흐름 (LLM 없음). 상세 404·필드 집합, 피드백 캐시 적중 0회·해시 변경 1회, 401·409·400·502는 `feedback_fn`·`profile_loader`·`profile_hash` 주입으로. `make_client`는 기본으로 관심회사 a·b를 넣고, resume·`lock_path`는 `tmp_path`를 넘겨 쓴다 (HOME에 락 파일을 만들지 않음)
- `tests/test_feedback.py`: fake `ask_json`으로 프롬프트 구성(프로필·본문·gaps), 본문 없을 때 대체, 5개 절단·0개 `LLMError`
- `tests/test_static.py`: tmp static 디렉토리로 클라이언트 경로 fallback, 자산 200·누락 자산 404, `/api/x` 404
- `tests/test_jobs.py`: `prepare`·`start`·`run`, 재진입 방지, breakdown 없는 공고 재판정·exclude hard delete, `is_locked` 세 경로(쓰기 없음), 취소 마감, 크래시(`kill -9`) 후 락 해제
- `tests/test_cli.py`: `cli.main(argv)` + `capfd`. 데모 골든 패스, JSON 키 집합(`posting`·`--body`·`--full` 포함), `posting` not_found·0.4.0 DB readonly(`applications` 없음)·지원완료(`postings` 제외, `posting` 마감 유지), exit 표 전부, subprocess로 stdout 순수성·SIGINT exit 130, 쓰기 불가 HOME에서 읽기 명령
- `tests/test_demo.py`: 데모 데이터 계약(회사·건수·등급 분포·마감), 고정 시각, `make_app()` 골든 패스(TestClient), 임시 경로 사용
- `tests/test_scrapers_live.py`: `LIVE=1`일 때만
