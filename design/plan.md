# PoC 0-1 ~ 0-6 실행 계획

## Context
본개발(Phase 1~3) 전에 남은 불확실성은 세 가지다: (1) 6개사 채용 공고를 코드로 안정적으로 가져올 수 있는가, (2) 이력서 기반 LLM 매칭이 납득 가능한 품질인가, (3) 전부 LLM 판정했을 때 시간·사용량이 감당 가능한가. 0-3/0-4(세션 인증)는 이미 통과했고, 이번에 0-1~0-6을 한 세션에서 끝낸다.

사용자 결정 사항:
- 범위: 0-1 ~ 0-6 전부
- 사전 필터: 회사별 공식 직군 분류(engineering/tech)로 1차 필터 후 LLM 판정 (Step 1 결과 보고 후 변경). 키워드 기반 추가 필터는 없음
- LLM 모델: Claude Opus 5.5 (`claude-opus-5-5`) 고정

Step 1 완료 (2026-10-09): 6개사 모두 가능. 판정표와 필터 기준은 `poc/README.md`

산출물은 모두 `poc/` 아래. 본개발 코드가 아니므로 구조는 가볍게, 단 `RawPosting` 모델과 스크래퍼 인터페이스는 Phase 1에서 그대로 옮길 수 있게 spec의 `Scraper` ABC 형태를 따른다.

## Step 1 — 데이터 소스 탐색 (0-1) ✅ 완료
결과(`poc/README.md`): 네이버 내부 JSON `loadJobList.do` + 상세 HTML / 카카오 `public/api/job-list` / 쿠팡·당근 Greenhouse Board API / 토스 자체 API(Greenhouse 스키마) / 라인 Gatsby page-data. 한국 기준 ~1,050건 → 엔지니어링 필터 후 ~340건. sandbox 도메인 추가 불필요.

## Step 2 — 회사별 스크래퍼 스크립트 (0-2)
- `poc/scrapers/base.py`: `RawPosting` (pydantic: company, external_id, title, apply_url, deadline|None, description|None, category|None, raw: dict) + spec의 `Scraper` ABC + registry
- `poc/scrapers/greenhouse.py`: 쿠팡·당근·토스 공통 베이스 (토스는 URL과 응답 래핑만 다름)
- `poc/scrapers/{naver,kakao,coupang,toss,daangn,line}.py`: 각 `fetch()` 구현. 한국 근무지 + 회사별 엔지니어링 분류 필터를 구현체 안에서 적용(`poc/README.md` 필터 표). `RawPosting.category`에 원본 분류 보존
- `poc/run_scrape.py`: `asyncio.gather`로 6개 병렬 실행 → `poc/out/<company>.json` 저장, 회사별 건수·소요 시간·실패 사유 출력
- 0-2 판정: 회사별로 필수 필드(title, apply_url, external_id) 100% 채워지는지, 선택 필드(deadline, 본문) 확보 여부를 README 표에 기록
- 본문(description): 네이버(상세 HTML `div.detail_wrap`)·라인(상세 page-data) 추가 호출, semaphore 5~10. 나머지는 목록 응답에 포함. HTML은 텍스트로 정리해 저장

## Step 3 — 프로필 추출 (0-5 전반)
- `poc/llm.py`: `poc/auth_check.py`의 호출 패턴(`query()` + `ResultMessage.structured_output`, `authentication_failed` 처리)을 공용화. `ClaudeAgentOptions(model="claude-opus-5-5", tools=[], setting_sources=[], output_format=json_schema)`
- `poc/profile.py`: `resume/resume.md` + `resume/career_portfolio.md` → 구조화 프로필 `poc/out/profile.json`
  - 스키마: core_skills, familiar_skills, domains, years, seniority, preferences(지역/비자/희망 도메인), dealbreakers
  - 파일 해시를 함께 저장해 재실행 시 캐시 (Phase 1 `matcher.py` 캐싱 규칙과 동일)

## Step 4 — 매칭 (0-5 후반)
- `poc/match.py`: 전체 공고를 N건 배치(초기 20건, 공고당 title + description 앞 1500자)로 LLM 판정. 출력 스키마: `[{external_id, fit: bool, score 0-100, summary, tech_stack[], fit_reason}]`
  - 프롬프트에 profile.json 전체 포함, 배치 간 동시성 3~4 (`asyncio.Semaphore`)
  - 결과 `poc/out/matches.json`, 적합 공고만 `poc/out/fit.md`로 사람이 읽기 좋게 정리
- 품질 평가: fit=true 상위 10건 + fit=false 중 무작위 10건을 사용자와 함께 검토. 오판 유형(과대/과소 적합, 이유 근거 부실)을 README에 기록하고 프롬프트 1회 수정 후 재실행

## Step 5 — 소요 시간·비용 측정 (0-6)
- `run_scrape.py`와 `match.py`에 단계별 타이머 → 전체 파이프라인 1회 실행 시간, LLM 호출 수, `total_cost_usd` 합계를 README에 기록
- 기준: 첫 실행(~340건 전체 판정, ~17회 호출)이 수 분 이내면 OK. 넘으면 배치 크기·동시성 조정 결과를 함께 기록. 이후 실행은 신규 공고만 판정하므로 훨씬 짧다는 점을 명시

## Step 6 — spec 반영
`design/spec.md`의 "PoC 결과"에 0-2/0-5/0-6 결과 추가. 선택한 배치 크기/동시성, 실측 시간·비용, Phase 1에서 바뀌어야 할 점을 적는다.

## 수정/생성 파일
- 생성: `poc/scrapers/base.py`, `poc/scrapers/greenhouse.py`, `poc/scrapers/<6개사>.py`, `poc/run_scrape.py`, `poc/llm.py`, `poc/profile.py`, `poc/match.py`, `poc/out/*` (gitignore 대상)
- 수정: `poc/pyproject.toml`(httpx, pydantic 추가), `poc/README.md`, `design/spec.md`(PoC 결과)
- 재사용: `poc/auth_check.py`의 SDK 호출 패턴

## 검증
- `uv run python run_scrape.py` → 6개사 모두 1건 이상, 필수 필드 누락 0, 실패 시 사유 출력
- `uv run python profile.py` → profile.json 생성, 두 번째 실행은 캐시 히트
- `uv run python match.py` → matches.json 생성, 배치 수 = ceil(공고 수/20), 샘플 20건 수동 검토 통과
- 전체 실행 시간·비용이 README와 spec에 기록됨

## 리스크
- Greenhouse/내부 API 스키마 변경 시 스크래퍼가 조용히 0건을 반환할 수 있음 → 0건이면 실패로 간주해 soft delete 방지 (spec sync 규칙과 일치)
- 첫 실행 비용은 수 달러 수준 예상(0-6에서 실측). 과하면 배치 크기 확대로 대응
- sandbox 도메인 차단 시 진행이 멈추므로, 차단 호스트가 나오면 즉시 모아서 요청
