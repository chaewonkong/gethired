# backend

FastAPI + sqlite. 채용 사이트 스크래핑(httpx) → 이력서 프로필 기반 LLM 판정(Claude Agent SDK) → 저장·조회 API.
설계 근거는 `../design/specs/`.

## 명령 (backend/에서)
```bash
UV_CACHE_DIR=../.uv-cache uv run pytest        # 단위·API 테스트, 네트워크/LLM 없음
LIVE=1 uv run pytest tests/test_scrapers_live.py  # 실제 사이트 호출
uv run uvicorn app.main:app --reload --port 8000
```
sandbox에서는 홈 uv 캐시에 쓸 수 없으므로 `UV_CACHE_DIR=../.uv-cache`를 붙인다.

## 흐름
`POST /api/scrape` → `JobManager.start()` → 프로필 로드 → 회사별 병렬로
fetch → `mark_seen` / `soft_delete_missing` → 미판정 공고만 `judge` → exclude 아닌 것만 `upsert_postings` → `record_judgments`

## 모듈
| 파일 | 역할 |
|---|---|
| `app/config.py` | 경로(`RESUME_DIR`, `DB_PATH`, `FRONTEND_DIST`), 매칭 배치 크기·동시성 |
| `app/scrapers/base.py` | `RawPosting`(정규화된 공고), `Scraper` ABC, `REGISTRY`(서브클래스 정의 시 자동 등록), `html_to_text`, `parse_date` |
| `app/scrapers/<company>.py` | 회사별 `fetch()`. 엔지니어링 직군 1차 필터는 여기서. 원본 분류는 `category`에 보존 |
| `app/scrapers/greenhouse.py` | Greenhouse 계열 공통 베이스 (쿠팡·당근·토스) |
| `app/llm.py` | `ask_json()`: Agent SDK structured output 래퍼. 모델 `claude-opus-5-5` 고정. 인증 실패는 `ClaudeAuthError` |
| `app/profile.py` | `resume/*.md` → `Profile`. 파일 이름·내용 해시로 `profile_cache`에 캐시 |
| `app/matcher.py` | 20건 배치 판정 → `Match`(fit_level/score/gaps/fit_reason). score 구간이 fit_level보다 우선. 누락 id는 재시도 |
| `app/repository.py` | sqlite 접근 전부. 테이블: `postings`, `judgments`, `bookmarks`, `scrape_runs`, `profile_cache` |
| `app/jobs.py` | 스크래핑 job 실행·상태(`Job`, `CompanyState`). 회사 단위 실패 격리, 세션 만료 시 `auth_required` |
| `app/api.py` | `create_app(repo, jobs, logged_in)`: `/api/{auth/status, companies, scrape, scrape/{id}, postings, postings/{id}/bookmark}` |
| `app/main.py` | 앱 조립 + `frontend/dist` 정적 서빙. `ANTHROPIC_API_KEY` 제거 |
| `scripts/` | 디버그용, 결과는 `out/`에 파일로. `run_scrape.py`(`just scrape`): 스크래퍼만 실행 + 건수·중복·본문 확보율 경고. `match.py`(`just match`): `out/*.json`을 판정해 `out/fit.md` 생성, `--planted`로 정답 공고 검증. DB는 `profile_cache`만 사용. `auth_check.py`: Agent SDK 세션 인증 확인 (PoC용) |

## 규칙
- LLM은 로컬 Claude Code 로그인 세션으로만 호출한다. API key를 쓰지 않는다
- 스크래핑은 결정적 코드(httpx)로. LLM은 프로필 추출과 매칭에만 쓴다
- 스크래퍼가 0건을 반환하면 실패로 처리한다 (soft delete 오작동 방지)
- 삭제는 soft delete(`deleted_at`). 공고가 다시 나타나면 복구된다
- `bookmarks.deleted_at`은 사용자 해제 전용. 공고 삭제 여부는 `postings`와 JOIN으로 판단
- exclude 판정은 `postings`에 저장하지 않고 `judgments`에만 기록한다 (재판정 방지)
- Agent SDK `query()` 제너레이터 안에서 raise하지 않는다 (aclose 충돌). 플래그를 세우고 루프 밖에서 raise
- 스키마 변경은 `CREATE TABLE IF NOT EXISTS`로 기존 `data/app.db`와 호환되게. 컬럼 추가는 마이그레이션 필요

## 새 회사 추가
1. `app/scrapers/<company>.py`에 `Scraper` 구현 (Greenhouse면 `GreenhouseScraper` 상속)
2. `app/scrapers/__init__.py` import 목록에 추가 (import 시 등록됨)
3. `fixtures/`에 응답 샘플 저장 + `tests/test_parsers*.py`에 파싱 테스트, `test_registry_has_all_companies` 갱신
4. 새 도메인은 `.claude/settings.json`의 sandbox `allowedDomains`에 추가

## 테스트
- `tests/test_parsers*.py`: `fixtures/`의 저장된 응답으로 파서 검증
- `tests/test_repository.py`: in-memory sqlite
- `tests/test_api.py`: `FakeScraper` + fake judge/profile로 job·API 전체 흐름 (LLM 없음)
- `tests/test_scrapers_live.py`: `LIVE=1`일 때만
