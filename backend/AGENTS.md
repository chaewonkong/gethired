# backend

FastAPI + sqlite. 채용 사이트 스크래핑(httpx) → 이력서 프로필 기반 LLM 판정(Claude Agent SDK 또는 Codex CLI) → 저장·조회 API.
설계 근거는 `../design/specs/`.

## 명령 (backend/에서)
```bash
UV_CACHE_DIR=../.uv-cache uv run pytest        # 단위·API 테스트, 네트워크/LLM 없음
LIVE=1 uv run pytest tests/test_scrapers_live.py  # 실제 사이트 호출
uv run uvicorn app.main:app --reload --port 8000
uv run gethired [serve] [--port 8000] [--no-open] [--demo]   # 설치형 진입점 (= python -m app)
uv run gethired auth [claude|codex] · reset-db · paths
uv run python -m app --demo --port 8000       # 데모 모드: 가짜 스크래퍼·판정, 임시 DB·이력서, 네트워크/LLM/CLI 없음
```
sandbox에서는 홈 uv 캐시에 쓸 수 없으므로 `UV_CACHE_DIR=../.uv-cache`를 붙인다.
데이터 경로 기본값은 platformdirs 사용자 디렉토리(`GETHIRED_HOME`). justfile은 `DB_PATH`·`RESUME_DIR`로 저장소 안(`backend/data/app.db`, `resume/`)을 가리킨다. 패키지(`gethired`, hatchling)는 `app/static/`(프론트 빌드)을 휠에 포함한다 (`just build-wheel`).

## 흐름
`POST /api/scrape` → `JobManager.start()` → 프로필 로드 → 회사별 병렬로
fetch → `mark_seen` / `soft_delete_missing` → 미판정 공고만 `judge` → exclude 아닌 것만 `upsert_postings` → `record_judgments`

### 구성
```
  [User]
     |
     v
+----------------------------------------+
| frontend (React)                       |
| tabs: Postings | Bookmarks | Hidden    |
|       | Companies                      |
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
     +--> scrapers/   -- httpx ---------> career sites (15)
     |
     +--> profile.py  -- read ----------> resume/*.md, *.pdf (pdf는 pypdf로 텍스트 추출)
     |                -- cache ---------> repository.py (profile_cache, key = resume hash)
     |                -- extract -------> LLM (provider CLI 로그인 세션)
     |
     +--> matcher.py  -- judge 20/batch -> LLM
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
 |     c. filter ............ 이미 판정한 공고 제외
 |     d. judge ............. 신규 공고만 LLM으로 20건씩 판정
 |     e. save .............. strong/good/stretch는 postings에 저장
 |                            exclude는 judgments에만 기록 (재판정 방지)
 |
 +-> 3. done
       frontend가 GET /api/postings로 목록 갱신 (등급, 북마크 여부 포함)
```
- 세션이 만료되면 job이 `auth_required`로 끝나고, 다음 실행에서 판정 못 한 공고만 다시 판정한다
- 북마크는 공고와 JOIN으로 묶여 있어서, 공고가 삭제되면 같이 숨겨지고 공고가 다시 나타나면 같이 돌아온다

## 모듈
| 파일 | 역할 |
|---|---|
| `app/config.py` | 경로(`HOME`=platformdirs 또는 `GETHIRED_HOME`, `DB_PATH`=`HOME/app.db`, `RESUME_DIR`=`HOME/resume`, `FRONTEND_DIST`=`app/static`), 매칭 배치 크기·동시성. env override: `GETHIRED_HOME`, `DB_PATH`, `RESUME_DIR`, `LLM_PROVIDER`, `LLM_TIMEOUT_S`, `CLAUDE_MODEL`, `CODEX_BIN`, `CODEX_MODEL` |
| `app/scrapers/base.py` | `RawPosting`(정규화된 공고), `Scraper` ABC, `REGISTRY`(서브클래스 정의 시 자동 등록), `html_to_text`, `parse_date` |
| `app/scrapers/<company>.py` | 회사별 `fetch()`. 엔지니어링 직군 1차 필터는 여기서. 원본 분류는 `category`에 보존 |
| `app/scrapers/greenhouse.py` | Greenhouse 계열 공통 베이스 (쿠팡·당근·토스) |
| `app/scrapers/greetinghr.py` | GreetingHR 계열 공통 베이스 (업스테이지·카카오페이). 공개 API가 없어 목록은 첫 페이지, 본문은 공고 페이지의 `__NEXT_DATA__`에서 꺼낸다 |
| `app/llm.py` | `ask_json()`: structured output 래퍼. `configure(provider)`로 모듈 상태를 두고 claude(Agent SDK) / codex(`codex exec` subprocess) 분기. 인증 실패는 `LLMAuthError`, 그 외 `LLMError`. codex는 호출 전 `is_logged_in` 선체크(미로그인 exec는 끝나지 않음), strict schema 변환(`to_strict_schema`), `-o` 파일로 결과, `--json`으로 usage·401 감지. runner는 `llm.codex_runner`로 주입 |
| `app/auth.py` | `is_logged_in(provider)`: claude는 `claude auth status` JSON, codex는 `$CODEX_BIN login status` exit code. provider별 single-flight |
| `app/profile.py` | `resume/*.md`·`*.pdf` → `Profile`. 본문은 `resume.extract_text`(문서당 50k자 상한). 파일 이름·내용 해시(1MB 청크)로 `profile_cache`에 캐시 |
| `app/resume.py` | `resume/` 파일 목록·저장·삭제·텍스트 추출. 파일명은 basename만, `.md`·`.pdf`만, 크기 제한 없음(임시 dotfile에 스트리밍 후 `os.replace`), 디렉토리 자동 생성, 같은 이름 덮어쓰기. `extract_text`: md는 그대로, pdf는 pypdf, `TEXT_LIMIT`(50k자) 초과는 잘라 `[이하 생략]`. 텍스트 없는 pdf는 저장 취소 + `ValueError`(API 400) |
| `app/matcher.py` | 20건 배치 판정 → `Match`(fit_level/score/gaps/fit_reason). score 구간이 fit_level보다 우선. 누락 id는 재시도 |
| `app/repository.py` | sqlite 접근 전부. 테이블: `postings`, `judgments`, `bookmarks`, `hides`, `interests`, `scrape_runs`, `profile_cache`, `settings`(key/value, `provider`). `now_iso()`는 `set_fixed_now()`로 고정 가능(데모 모드) |
| `app/jobs.py` | 스크래핑 job 실행·상태(`Job`, `CompanyState`). job 시작 시 settings의 provider로 `llm.configure()`, job 전체가 그 provider로 고정(`Job.provider`). 회사 단위 실패 격리, 세션 만료 시 `auth_required` |
| `app/api.py` | `create_app(repo, jobs, logged_in: (provider) -> bool, resume_dir)`: `/api/{settings/provider, auth/status, companies, companies/{c}/interest, interests, scrape, scrape/{id}, postings, postings/{id}/bookmark, postings/{id}/hide, resume, resume/{name}}`. `GET settings/provider`는 DB만(`{provider, chosen}`), `auth/status`는 CLI 실행. `PUT settings/provider`는 job 실행 중 409, 저장 후 auth status 반환. 미로그인 scrape는 401 `{code: "login_required", provider, message}` |
| `app/main.py` | 앱 조립 + `app/static` 정적 서빙. `ANTHROPIC_API_KEY`·`OPENAI_API_KEY` 제거 |
| `app/__main__.py` | 콘솔 진입점 `gethired`: `serve`(기본, 브라우저 오픈, `--no-open`·`--demo`)·`auth`·`reset-db`·`paths`. `uvicorn.run`에 app 객체를 넘긴다 |
| `app/demo.py` | 데모 모드(`python -m app --demo`, README GIF 녹화용). 토스·당근·카카오·네이버 가짜 스크래퍼(`register=False`, 공고 8건) + 고정 프로필·판정(strong 2 · good 3 · stretch 3), `logged_in` 항상 True, `set_fixed_now("2026-10-18T09:00:00+09:00")`. `DB_PATH`/`RESUME_DIR` env가 없으면 임시 디렉토리. `DEMO_JUDGE_DELAY_S`(기본 0.7)로 진행 상태 노출. `GETHIRED_DEMO=1`일 때만 모듈 수준 `app` 생성 |
| `scripts/` | 디버그용, 결과는 `out/`에 파일로. `run_scrape.py`(`just scrape`): 스크래퍼만 실행 + 건수·중복·본문 확보율 경고. `match.py`(`just match`): `out/*.json`을 판정해 `out/fit.md` 생성, `--planted`로 정답 공고 검증, `--provider`로 하네스 선택. DB는 `profile_cache`만 사용. `resume_text.py`(`just resume-text`): 이력서 텍스트 추출 결과를 `out/resume_text/`에 저장. `auth_check.py`: Agent SDK 세션 인증 확인 (PoC용) |

## 규칙
- LLM은 선택한 provider CLI(Claude Code / Codex)의 로컬 로그인 세션으로만 호출한다. API key를 쓰지 않는다
- Claude Code sandbox 안에서는 실제 `codex exec`가 실패한다(`~/.codex` 쓰기 불가). codex 경로는 runner fake로 테스트하고, 라이브 확인은 sandbox 밖에서
- 스크래핑은 결정적 코드(httpx)로. LLM은 프로필 추출과 매칭에만 쓴다
- 스크래퍼가 0건을 반환하면 실패로 처리한다 (soft delete 오작동 방지)
- 삭제는 soft delete(`deleted_at`). 공고가 다시 나타나면 복구된다
- `bookmarks.deleted_at`·`hides.deleted_at`은 사용자 해제 전용. 공고 삭제 여부는 `postings`와 JOIN으로 판단
- exclude 판정은 `postings`에 저장하지 않고 `judgments`에만 기록한다 (재판정 방지)
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
- `tests/test_repository.py`: in-memory sqlite
- `tests/test_resume.py` · `tests/test_profile.py`: 텍스트 추출(`fixtures/resume_sample.pdf`, `resume_blank.pdf`는 합성 PDF), 절단, 프로필 문서 구성·해시
- `tests/test_llm.py` · `tests/test_llm_codex.py` · `tests/test_auth.py`: provider 분기, strict 변환, codex 출력 파싱(`fixtures/codex_*.jsonl`, 실측 출력), 인증 판별, single-flight. 실제 CLI 실행 없음. `conftest.py`가 매 테스트 후 `configure("claude")`
- `tests/test_api.py`: `FakeScraper` + fake judge/profile로 job·API 전체 흐름 (LLM 없음). `make_client`는 기본으로 관심회사 a·b를 넣고, resume는 `tmp_path`를 넘겨 쓴다
- `tests/test_demo.py`: 데모 데이터 계약(회사·건수·등급 분포·마감), 고정 시각, `make_app()` 골든 패스(TestClient), 임시 경로 사용
- `tests/test_scrapers_live.py`: `LIVE=1`일 때만
