# spec - 공고 상세 화면
## 목표
- 공고 상세 화면을 만든다
- 상세에서 공고 내용, 내 이력서와 공고 각 항목의 정합성, 공고 기준 이력서 피드백을 확인할 수 있다

## 목표가 아닌 것
- 이력서 자동 재작성
- 공고 전문을 상세의 기본 화면에 펼쳐 보여주는 것 (접힌 참고용으로만)
- 피드백 배치 생성 (스크래핑 시 자동 생성하지 않는다)
- CLI에서 피드백 생성 (읽기만)
- exclude 판정 공고의 상세

## 기능
### 저장 데이터 확장
- 공고 본문(`description`, 스크래퍼의 텍스트 변환 결과)을 그대로 저장한다. 저장 공고는 exclude 제외 수백 건, 평균 3~4KB라 용량 문제 없음. 본문은 판정·저장 시점에만 들어가고 이후 재방문(`mark_seen`)으로는 갱신하지 않는다 (summary와 같은 수명)
- 판정 시 LLM이 공고 본문에서 아래를 추출해 저장한다. 회사별로 본문 구조가 달라 원문 섹션 분리는 하지 않는다
  - `summary` (기존)
  - `requirements: list[str]` 자격요건. 최대 8개, 한 줄 80자 이내
  - `preferred: list[str]` 우대사항. 같은 상한
- 판정 입력 본문 한도를 2500자에서 6000자로 올린다. 우대사항이 본문 뒤쪽에 있어 2500자로는 토스·당근·크래프톤 공고의 절반 이상이 잘렸다. 배치 크기는 20 → 10으로 줄여 응답 길이와 타임아웃을 상쇄한다
- 정합성은 단일 `score` 외에 배점 축별로 쪼개 저장한다. 축과 만점은 현재 프롬프트 배점과 같다

| 축 | 키 | 만점 |
|---|---|---|
| 핵심 기술 | `skills` | 35 |
| 도메인·업무 성격 | `domain` | 35 |
| 연차·시니어리티 | `seniority` | 20 |
| 우대사항 | `preferred` | 10 |

- `Match.breakdown: {skills, domain, seniority, preferred}`. 합계는 `score`와 같아야 한다 (불일치 시 `score`를 합계로 맞춘다. `fit_level`은 기존처럼 `score` 구간으로 보정)
- 기존 판정(breakdown 없음)은 다음 스크래핑 때 judgments 캐시를 무시하고 재판정한다. 1회성 비용. 재판정 결과가 exclude면 기존 행을 북마크·숨김·피드백과 함께 hard delete한다 (exclude는 원래 저장하지 않는 데이터. 북마크된 공고도 예외 없음, job 결과의 `excluded` 건수에 포함)

### 상세 화면
- 라우터를 도입한다 (react-router-dom). 탭도 경로가 된다: `/` 공고 · `/bookmarks` · `/hidden` · `/companies`. 상세는 `/postings/:id`
- 백엔드 정적 서빙은 클라이언트 경로를 `index.html`로 fallback한다 (현재 `StaticFiles(html=True)`는 `/postings/1`을 404로 응답)
- 리스트(공고·북마크·숨김 탭)에서 카드를 클릭하면 상세로 이동한다. 별표·숨김·지원 링크 클릭은 상세로 이동하지 않는다
- 뒤로가기 시 리스트의 탭·필터·스크롤 위치(불러온 건수 포함)가 복원된다. 탭 버튼으로 돌아오면 맨 위. 상세 진입 시에도 맨 위로
- 상세의 "목록으로"는 히스토리가 있으면 뒤로가기, URL로 직접 진입했으면 `/`
- 상세 구성
  - 헤더: 회사, 제목, fit_level, score, 마감, 지원 링크, 북마크·숨김 토글
  - 공고: summary, requirements, preferred, tech_stack. 맨 아래 접힌 본문 (저장된 경우만)
  - 정합성: 축별 점수 / 만점 막대 4개, fit_reason, gaps. breakdown이 없는 기존 판정은 "다음 스크래핑 때 재판정" 안내
  - 피드백: 아래 참조
- 삭제된(deleted_at) 공고는 상세를 볼 수 없다. 404와 함께 목록으로 돌아가는 링크를 보여준다
- 상세는 라우트 단위 데이터라 `PostingDetail`이 직접 fetch한다. "데이터는 App에서만 fetch" 규칙의 명시적 예외. 북마크·숨김 상태는 App의 목록에서 id로 읽는다

### 이력서 피드백
- 상세에 "피드백 생성" 버튼을 둔다. 누르면 그때 LLM을 호출한다 (lazy)
- 입력: 프로필 + 공고 본문 + gaps (requirements·preferred는 보조. 본문이 없는 기존 판정은 summary·requirements로 대체). 출력: 이력서에서 보강·강조할 점 3~5개, 각각 "항목: 설명" (개수는 프롬프트 지시. 5개 초과는 잘라내고 0개만 오류). gaps는 공고 대비 부족한 점, 피드백은 그걸 이력서에서 어떻게 메우거나 드러낼지로 역할을 나눈다. 이력서에 없는 경험을 지어내게 하지 않는다
- 결과는 `feedbacks(posting_id, profile_hash, items, created_at)`에 저장한다. 같은 공고·같은 프로필이면 재호출 없이 캐시를 보여준다. 이력서가 바뀌면(profile_hash 변경) 버튼이 다시 나타나고 이전 피드백은 "이전 이력서 기준"으로 접어 둔다
- 버튼은 로그인 상태를 미리 확인하지 않고 항상 보인다. 생성 요청이 401이면 그 자리에 로그인 안내(기존 `login_required` 처리와 동일). 로그인이 확인되면 안내는 다시 버튼으로 돌아간다
- 상세의 북마크·숨김 상태는 목록 상태를 우선 쓰고, 목록에 없는 공고(직접 진입, 관심회사 아님)는 상세 응답 값을 쓴다
- 생성 중에는 버튼 비활성 + 로딩 표시
- 스크래핑 job이 실행 중이면 피드백 생성은 막는다 (프로세스 간 락 확인). 확인은 시작 시점 1회. 생성 도중 스크래핑이 시작되는 것은 허용
- breakdown·requirements가 없는 기존 판정 공고에서도 생성할 수 있다

### API
- `GET /api/postings/{id}`: 상세 1건. 목록 응답 필드 + `description`, `requirements`, `preferred`, `breakdown`, `feedback` (없으면 null). 삭제된 공고는 404
- `POST /api/postings/{id}/feedback`: 피드백 생성 후 반환. 캐시가 있으면 LLM 호출 없이 반환. 오류: 삭제·없음 404, job 실행 중 409 `job_running`, 미로그인 401 `login_required`, 이력서 파일 없음 400 `no_resume`, LLM 실패 502 `llm_error`
- `GET /api/postings` 목록 응답에 `breakdown` 추가 (카드에서 쓰지 않더라도 CLI와 공유)

### CLI · 스킬
- `gethired posting <id> [--json] [--body]`: 상세 1건. 피드백은 캐시된 것만 포함 (`feedback` 또는 null). 본문은 `--body`일 때만 (에이전트 컨텍스트 절약). 삭제·미존재는 `not_found` 코드
- `postings --full`에 `breakdown` 추가
- `plugin/skills/jobs/SKILL.md`에 `posting <id>` 사용법과 응답 키를 추가한다. 키 집합은 `backend/tests/test_cli.py`와 맞춘다

### 데모
- `demo.py` 가짜 판정에 description·requirements·preferred·breakdown을 넣고, 피드백 생성은 고정 응답으로 흉내낸다
- 데모 녹화에 상세 진입과 피드백 생성 1회를 추가하고 `docs/demo.gif`를 갱신한다

## 검증 방법
- pytest
  - `breakdown` 합계 = `score`. 불일치 샘플은 `score`가 합계로 보정된다
  - breakdown 없는 기존 행은 다음 스크래핑에서 재판정 대상에 포함된다. 재판정이 exclude면 행과 북마크·숨김·피드백이 삭제된다
  - `GET /api/postings/{id}` 삭제 공고 404. `POST .../feedback` 캐시 적중 시 LLM 호출 0회, profile_hash 변경 시 1회. 401·409·400·502 각 1건
  - `posting <id> --json` 키 집합이 SKILL.md와 일치. `--body`일 때만 `description`. 0.4.0 DB를 readonly로 열어도 오류 없이 `feedback`·`breakdown` null
- vitest
  - 카드 클릭 → `/postings/:id` 이동. 별표·숨김 클릭은 이동하지 않음
  - 뒤로가기 시 탭·필터·스크롤·불러온 건수 복원. 직접 진입 시 "목록으로"는 `/`
  - 피드백 버튼: 미생성 → 버튼, 생성 중 → 로딩, 생성 후 → 본문, 401 → 로그인 안내, 이전 이력서 기준 → 접힘 + 버튼
- 수동
  - `/postings/1`을 새 탭에서 직접 열어 서버 fallback 확인
  - 상세의 접힌 본문과 requirements·preferred 대조
  - 이력서 교체 후 같은 공고 상세에서 버튼이 다시 보이고 이전 피드백이 접힘

## 결정 사항 (2026-10-20)
- 공고 본문을 그대로 저장한다 (용량 수 MB). 상세에서는 접힌 참고용으로만 보여주고, summary·requirements·preferred를 판정 시 LLM이 추출해 기본 화면에 쓴다
- 판정 입력 한도 2500 → 6000자, 배치 20 → 10건. 추출 목록은 각 최대 8개·80자, breakdown 축 범위도 같은 방식 (프롬프트 지시 + 코드에서 잘라냄·clamp, 스키마 검증으로 강제하지 않음. 한 건 검증 실패가 배치 전체 재시도로 번지는 것을 피함)
- 정합성은 4축 breakdown으로 쪼개 저장한다. 축과 배점은 기존 프롬프트 그대로
- 재판정에서 exclude가 된 기존 공고는 hard delete (북마크 포함)
- 피드백은 상세의 버튼으로 lazy 생성하고 profile_hash 단위로 캐시한다. 입력은 본문 우선
- 라우터를 도입하고 탭도 경로로 바꾼다. 상세 fetch는 "App에서만 fetch" 규칙의 예외
- 삭제된 공고는 상세를 볼 수 없다
- `GET /api/postings/{id}`, `POST /api/postings/{id}/feedback`, CLI `posting <id> [--body]`를 추가하고 스킬을 갱신한다
