# job-posting
등록해둔 회사들의 채용사이트를 읽어, 사용자가 지원할 만한 포지션들을 리스팅해 주는 서비스

## 설계
- backend: python으로 scraper 개발 + fastapi, pydantic
- frontend: react로 개발
- db: sqlite 사용
- llm: Claude Agent SDK (`claude-agent-sdk`, python)
  - 인증: API key 사용 안 함. 로컬 Claude Code 로그인 세션(`claude login`)을 그대로 사용
  - `ANTHROPIC_API_KEY` 환경변수가 설정되어 있으면 세션보다 우선 적용되므로 반드시 unset 상태로 실행
  - 개인 로컬 용도로만 사용 (구독 세션 인증이라 외부 배포/서비스화 불가)
  - 모델: Claude Opus 5.5 고정 (`ClaudeAgentOptions(model="claude-opus-5-5")`)
  - 용도: 이력서 프로필 추출, 공고 적합도 판정 + 이유 생성. 도구는 비활성화하고 JSON 응답만 받아 pydantic으로 검증
  - 스크래핑은 LLM이 아닌 결정적 코드(httpx)로 수행

## 기능
- resume 디렉토리의 resume.md, career_portfolio.md를 읽고 사용자의 특징을 추출한다.
- 사용자에게 적합한 job posting을 등록 회사들에서 서칭한다
- 적합한 공고를 찾은 경우 sqlite DB에 저장한다
  - 스크래핑 일자
  - 공고 마감일 (nullable)
  - 포지션 개요
  - 기술 스택
  - 공고가 사용자에게 맞는 이유
  - 지원 링크
  - deleted_at
- web page를 통해 리스트로 저장된 공고를 확인할 수 있다.
- 과거 공고가 사라진 경우 deleted_at에 날짜를 기록해 soft delete한다
- 공고는 병렬로 스크래핑한다.

## Web 기획
UI 샘플: [ui-sample.html](ui-sample.html)

- 톤 (확정): 흰 배경, 다크모드 미지원. 밝고 희망적인 느낌. 채도 낮은 하늘색 계열 (로고만 sunrise 그라데이션 `#7dd3fc → #a5f3fc → #fef3c7`, 주 버튼 단색 `#7dd3fc`, 텍스트 `#0369a1`/`#0c4a6e`, 배경 `#f0f9ff`) + 쿨그레이 뉴트럴, 둥근 사각 버튼, 얇은 그림자 카드, 해돋이 아이콘 로고
- 레이아웃: 모바일 퍼스트 반응형. 콘텐츠 최대 너비 800px, 그 이하에서는 화면 너비에 맞춤 (좌우 16px 여백)
  | 너비 | 공고 탭 | 회사 탭 |
  |---|---|---|
  | < 480 | 툴바 세로 스택, 카드 1열, 진행 2열 | 카드형 |
  | 480–639 | 툴바 2단(버튼+필터 / 메타), 카드 1열, 진행 3열 | 카드형 |
  | ≥ 640 | 툴바 1줄, 카드 1열, 진행 1줄 | 테이블 |
  - 공고 카드는 모든 너비에서 한 줄에 하나
- 페이지는 tab으로 구분한다: **공고** / **회사**

### 공고 탭 (기본)
- 진입 시 스크래핑하지 않는다. DB에 저장된 공고 중 `deleted_at IS NULL`인 것만 리스팅한다
- "스크래핑 하기" 버튼을 누를 때만 스크래퍼가 동작한다
  - 진행 중에는 버튼 비활성화 + 회사별 loading 상태 표시
  - 완료 후 리스트 갱신
  - 세션 만료 시 로그인 안내 표시 (아래 "세션 만료 처리")
- 각 공고 항목: 회사, 포지션 개요, 기술 스택, 맞는 이유, 마감일, 지원 링크, 스크래핑 일자
- 회사 필터

### 회사 탭
- 등록된 회사 목록 조회 (UI에서 추가/수정 불가)
- 항목: 회사명, 채용사이트 링크, 마지막 스크래핑 일시, 마지막 결과 (성공 / 실패 + 사유)
- 회사 목록은 코드에 구현된 스크래퍼 구현체 기준이다. 새 회사 추가 = 스크래퍼 구현체 추가

## 스크래퍼 구조
- `Scraper` 추상 클래스로 인터페이스를 정의하고, 회사별 구현체를 둔다
  ```python
  class Scraper(ABC):
      company: ClassVar[str]          # "naver"
      display_name: ClassVar[str]     # "네이버"
      careers_url: ClassVar[str]      # 채용사이트 링크

      @abstractmethod
      async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]: ...
  ```
- 구현체는 registry에 등록되고, 회사 탭과 스크래핑 대상은 registry에서 가져온다
- 공통 ATS(예: Greenhouse)를 쓰는 회사가 있으면 ATS 베이스 클래스를 두고 구현체는 board id만 지정
- 각 구현체는 회사의 공식 직군 분류로 엔지니어링 공고만 남긴다 (한국 근무지 기준). 분류가 없는 회사는 제목 키워드로 대신한다. 원본 분류값은 `RawPosting.category`에 보존

## 검증 방법
- 등록 회사별 스크래퍼가 오류 없이 job posting을 가져온다
- claude code session이 만료될 경우 적절한 안내를 통해 사용자에게 로그인이 필요함을 알린다.

## 데이터 모델
`postings`
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| company | TEXT | |
| external_id | TEXT | 회사 내 공고 고유 ID. (company, external_id) UNIQUE |
| title | TEXT | |
| summary | TEXT | 포지션 개요 |
| tech_stack | TEXT (JSON array) | |
| fit_reason | TEXT | 사용자에게 맞는 이유 |
| apply_url | TEXT | |
| deadline | DATE NULL | |
| scraped_at | DATETIME | 최초/최근 스크래핑 일자 |
| deleted_at | DATETIME NULL | |

- sync 규칙: 회사별 스크랩 성공 시, 이번 결과에 없는 external_id는 `deleted_at = now`. 다시 나타나면 `deleted_at = NULL`
- 스크랩 실패한 회사는 soft delete 판정 대상에서 제외 (일시 장애로 전부 삭제되는 것 방지)
- 이미 판정된 공고(external_id 존재)는 LLM 재판정하지 않음

`scrape_runs` (회사 탭의 마지막 스크래핑 결과용)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| company | TEXT | |
| started_at | DATETIME | |
| finished_at | DATETIME NULL | |
| status | TEXT | running / done / failed / auth_required |
| error | TEXT NULL | 실패 사유 |
| fetched_count | INTEGER NULL | |

## API
- `GET /auth/status` → `{logged_in: bool}`. `claude auth status` 기반
- `GET /companies` → registry 회사 목록 + 회사별 마지막 `scrape_runs` 결과
- `POST /scrape` → `{job_id}`. 진행 중인 job이 있으면 그 job_id 반환. 세션 만료 시 `401 {code: "claude_login_required"}`
- `GET /scrape/{job_id}` → 회사별 진행 상태 (pending / running / done / failed). 진행 중 세션 만료 시 job 상태 `auth_required`
- `GET /postings?company=` → `deleted_at IS NULL`만 반환

## 세션 만료 처리
- "스크래핑 하기" 클릭 시 `POST /scrape`가 세션을 선확인. 만료 시 스크래핑을 시작하지 않고 안내 표시
  - 안내 문구: 터미널에서 `claude login` 실행 후 다시 시도
- 스크래핑 도중 LLM 호출이 인증 오류로 실패하면 job을 `auth_required`로 종료
  - 이미 수집된 raw 공고는 버리지 않음. 재로그인 후 재실행 시 미판정 공고만 판정
- 세션 만료 상태에서도 기존 DB 공고 리스트는 조회 가능

## 개발 계획

### Phase 0 — PoC (본개발 전 가능성 타진)
| # | 검증 항목 | 성공 기준 |
|---|---|---|
| 0-1 | 회사별 데이터 소스 탐색 (내부 JSON API / ATS / SSR HTML) | 6개사 모두 스크립트로 공고 목록 획득 |
| 0-2 | 필드 확보 여부 | 필수: title, apply_url, external_id / 선택: deadline, 본문, 기술스택 |
| 0-3 | Agent SDK 세션 인증 | API key 없이 `query()` 호출 성공 |
| 0-4 | 세션 만료 감지 | 로그아웃 상태에서 SDK가 반환하는 에러 타입/메시지를 식별하고 구분 가능 |
| 0-5 | 프로필 추출 + 매칭 품질 | 샘플 공고 20건에 대해 적합 판정과 이유가 납득 가능 |
| 0-6 | 병렬 수집 + 매칭 소요 시간 | 첫 실행 기준 허용 가능한 시간 측정 (목표 수십 초 단위) |

결과물: `poc/` 회사별 스크립트 + 회사별 판정표 (가능 / 우회 필요 / 불가)

#### PoC 결과
- 0-1 ✅ 6개사 모두 브라우저 없이 httpx로 공고 목록 확보 (상세 표: `poc/README.md`)
  - 네이버: 내부 JSON `loadJobList.do` + 상세 HTML / 카카오: `public/api/job-list` / 쿠팡·당근: Greenhouse Board API / 토스: Greenhouse 스키마를 자체 API로 프록시 / 라인: Gatsby page-data(Strapi)
  - 쿠팡 사이트는 Cloudflare challenge지만 Greenhouse API로 우회. 글로벌 공고라 `location`에 Korea 포함만 사용
- 0-2 ✅ 필수 필드(external_id, title, apply_url) 6개사 확보. deadline은 네이버/카카오/라인만 실질 제공, 나머지는 null
  - 본문은 네이버·라인만 상세 1회 추가 호출 필요 (각 23건/61건)
  - 한국 기준 수집량 ≈ 1,050건 → 회사별 공식 엔지니어링 분류로 필터 후 ≈ 340건 (네이버 `Tech`, 카카오 `TECHNOLOGY`, 토스 Job Category, 당근 `Division=Tech`, 라인 `job_unit=Engineering`, 쿠팡은 분류가 없어 제목 키워드). 상세: `poc/README.md`
- 0-3 ✅ `claude-agent-sdk`가 API key 없이 `claude.ai` 세션으로 동작 (sandbox 내부 포함)
  - `tools=[]`, `setting_sources=[]`, `output_format={"type":"json_schema",...}` → `ResultMessage.structured_output`으로 dict 수신
  - 단순 호출 1회 약 5.5초, $0.025 (구독 사용량 차감 기준 추정치)
- 0-4 ✅ 미인증 감지 (`CLAUDE_CONFIG_DIR=<빈 디렉토리>`로 재현)
  - 스트림 중 `AssistantMessage.error == "authentication_failed"` → 이후 `ResultError("Not logged in · Please run /login")` raise. 0.3초 내 실패
  - 사전 체크: `claude auth status` → JSON `loggedIn` (미인증 시 exit 1). `/auth/status`는 이걸로 구현
  - 미검증: 토큰 "만료"(로그인 이력 있음) 케이스가 같은 신호인지는 재현 불가. `authentication_failed` + `api_error_status == 401` 둘 다 auth 오류로 처리
- 0-5 ✅ 프로필 추출 + 매칭 (상세: `poc/README.md` Step 3/4)
  - 프로필: 이력서 2개 → 구조화 JSON, 21.5초, $0.138. 이력서 해시로 캐시. 희망 근무지/비자 등은 이력서에 없어 비어 있음 → **Phase 1: 희망 조건을 별도 입력(설정 파일)으로 받아 프로필에 병합**
  - 매칭: 322건 + 플랜티드 3건, 배치 20 → 누락 0, 플랜티드 3/3, 결정성 20/20, fit 22건(토스 14, 당근 6, 라인 1). 품질 샘플 검토는 사용자 대기 (`poc/results/fit.md`)
  - Phase 1 반영: 본문 1500자 제한에 요구사항이 잘리는 공고 있음 → 2500자 이상 또는 요구사항 섹션 우선. fit_reason이 이력서의 구체 경험을 인용하도록 한 프롬프트 규칙은 유지
- 0-6 ⚠️ 시간 ✅ / 비용 ❌ (상세: `poc/README.md` Step 5)
  - 첫 실행 325건: 226초(3.8분), 17회 호출, $5.86 상당 (목표 $5). 입력 489K / 출력 103K 토큰. 동시성 4로 순차 대비 약 4배
  - 증분 실행(신규 0건): 호출 0, 0.5초 → 운영 비용은 신규 공고 수에 비례
  - 비용 절감은 Phase 1에서 선택: 저점수 공고의 fit_reason 축약, 배치 30, 프롬프트 캐시 유지(시스템 프롬프트·프로필을 앞에 고정)
- 환경 메모: sandbox에서 uv 캐시 쓰기 불가 → `UV_CACHE_DIR=<프로젝트>/.uv-cache` 사용

#### PoC 결론
6개 항목 중 비용만 목표를 소폭 초과. 본개발 진행 가능. Phase 1에 반영할 사항은 위 각 항목의 "Phase 1" 메모 참조.

#### PoC 검증 계획 (Step 2~6, `design/plan.md` 기준)
기준값(5분, $5, 80%, ±30%)은 초기 가정이며 실측 후 조정한다. 사람이 직접 봐야 하는 항목은 **(사람)** 표시.

**Step 2 — 스크래퍼 (0-2)**
| 검증 | 방법 | 통과 기준 |
|---|---|---|
| 실제 수집 | `uv run python run_scrape.py` | 6개사 모두 ok, 1건 이상 |
| 필수 필드 | 저장 전 pydantic 검증 | external_id/title/apply_url 누락 시 해당 회사 failed. 누락 0건 |
| 필터 동작 | 회사별 `category` 분포 출력 | `poc/README.md` 필터 표와 일치 |
| 건수 sanity | 회사별 건수 vs README 예상치 | ±30% 이내. 벗어나면 스키마 변경 의심 경고 |
| 중복 | `(company, external_id)` 유니크 검사 | 중복 0 |
| 본문 확보율 | `description` 100자 이상 비율 | 회사별 95% 이상 |
| apply_url 유효성 | 회사별 무작위 3건 요청 | 200 (리다이렉트 허용) |
| 파서 단위 테스트 | Step 1 응답을 `poc/fixtures/<company>.json`으로 저장, `pytest poc/tests/test_parsers.py` | 네트워크 없이 fixture → `RawPosting` 변환, 필터·날짜 파싱(네이버 `endYmd`, 라인 `until_filled`) 통과 |
| 실패 격리 | 한 회사 URL을 일부러 깨뜨려 실행 | 그 회사만 failed, 나머지 5개 정상 |

**Step 3 — 프로필 추출**
| 검증 | 방법 | 통과 기준 |
|---|---|---|
| 스키마 | `profile.json`을 pydantic 모델로 로드 | 필수 키 존재, `core_skills` 비어 있지 않음 |
| 내용 정확성 (사람) | 추출 결과를 이력서와 대조 | 주력 스택이 core에, 매치메이킹이 domains에, 희망 근무지·비자 조건이 preferences에 있음. 이력서에 없는 기술 0건 |
| 캐시 | 두 번 실행 | 두 번째는 LLM 호출 없이 즉시 종료. `resume.md` 한 줄 수정 시 재호출 |
| 인증 실패 | `CLAUDE_CONFIG_DIR=<빈 dir>`로 실행 | `ClaudeAuthError`로 종료, traceback 없이 안내 메시지 |

**Step 4 — 매칭 (0-5)**
| 검증 | 방법 | 통과 기준 |
|---|---|---|
| 출력 완전성 | 입력 공고 수 vs `matches.json` 항목 수 | 1:1. 빠진 external_id가 있으면 해당 배치만 재시도 |
| 스키마 | 각 항목 pydantic 검증 | score 0~100, fit bool, fit_reason 20자 이상, tech_stack 리스트 |
| 결정성 | 같은 배치 2회 실행 | fit 판정 일치율 90% 이상 |
| 플랜티드 테스트 | 가짜 공고 3건 혼입: ① Go 매치메이킹 백엔드 (fit) ② iOS 앱 개발 (unfit) ③ 영업 관리자 (unfit) | 3건 모두 기대대로 |
| 품질 (사람) | fit=true 상위 10 + fit=false 무작위 10을 `fit.md`로 검토 | 오판 4건 이하. fit_reason이 이력서의 구체 경험을 인용 |
| 배치 경계 | 마지막 배치(나머지) 처리 | 총 배치 수 = ceil(N/20) |

**Step 5 — 시간·비용 (0-6)**
| 검증 | 방법 | 통과 기준 |
|---|---|---|
| 전체 파이프라인 | scrape → profile → match 연속 실행, 단계별 타이머 | 첫 실행 총 5분 이내 (10분 초과 시 실패) |
| 비용 | `ResultMessage.total_cost_usd` 합산 | 첫 실행 $5 이하. 초과 시 배치 크기 조정 후 재측정 |
| 증분 실행 | 2회차 실행 (판정 완료 공고 스킵) | LLM 호출 0~1회, 1분 이내 |
| 동시성 효과 | 매칭 동시성 1 vs 4 비교 | 4가 유의미하게 빠르고 rate limit 에러 없음 |

**Step 6 — spec 반영**
- PoC 결과 섹션에 0-2/0-5/0-6 각각 ✅/❌와 실측 수치, Phase 1에서 바뀔 점 기록
- 위 검증 항목 중 파서 fixture 테스트·플랜티드 테스트·실패 격리는 Phase 3 테스트로 그대로 승계

### Phase 1 — Backend
- `scrapers/base.py`: `Scraper` ABC + registry
- 회사별 스크래퍼 6개, `asyncio.gather` + `httpx.AsyncClient` 병렬 실행
- `llm.py`: Agent SDK 래퍼. 인증 오류를 `ClaudeAuthError`로 변환
- `matcher.py`: 프로필 캐싱(이력서 파일 해시 기준), 신규 공고만 배치로 LLM 판정
- `repository.py`: sqlite upsert + soft delete sync
- FastAPI 엔드포인트 + 백그라운드 scrape job

### Phase 2 — Frontend
- React (Vite)
- 탭: 공고 / 회사
- 공고 탭: 진입 시 `GET /postings` 렌더링. "스크래핑 하기" → `POST /scrape` → 폴링하며 회사별 loading 표시 → 완료 후 재조회
- 회사 탭: `GET /companies` 렌더링
- 세션 만료 안내 배너, 회사 필터

### Phase 3 — 검증
- 회사별 스크래퍼 통합 테스트: 실제 호출, 1건 이상 + 필수 필드 존재
- 응답 fixture 기반 파서 단위 테스트
- soft delete sync 단위 테스트
- 세션 만료 시나리오 테스트: `ClaudeAuthError` 발생 시 job 상태 `auth_required`, API 401 응답 확인

## 등록해둔 회사
- 네이버
- 카카오
- 쿠팡
- 토스
- 당근
- 라인
