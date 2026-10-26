# spec - 지원완료 상태 추가

## 문제제기
- 지원한 공고가 공고·북마크 탭에 계속 남아 아직 지원하지 않은 공고와 섞인다
- 숨김으로 대신하면 "관심 없음"과 "지원함"이 구분되지 않고, 어디에 지원했는지 모아 볼 곳이 없다

## 목표
- 각 공고에는 지원완료 상태가 있으며 지원완료 상태인 공고는 공고·북마크 탭에서 제외된다
- 지원한 공고만 모아 보는 지원완료 탭이 추가된다

## 목표가 아닌 것
- 지원 이후 단계 추적 (서류합격·직무인터뷰·인성면접·처우협의 등). 후속 spec에서 다룬다. 이번에는 데이터 모델·API만 확장 가능하게 둔다
- 공고별 메모, 지원일 수정
- 숨김과의 통합
- 데모 모드(`demo.py`)·README GIF 반영

## 기능
- 목록(PostingCard)에 지원완료 버튼을 둔다. 북마크·숨김 버튼 옆
- 상세(PostingDetail)에도 지원완료 버튼을 둔다
- 지원완료 버튼을 누르면 해당 공고는 지원완료 상태가 되고, 지원 시각이 기록된다
- 다시 누르면 지원완료가 해제된다 (토글. 실수 복구용)
- 공고·북마크·회사 외에 지원완료 탭을 추가한다
- 지원완료 공고는 공고·북마크 탭에 보이지 않으며, 지원완료 탭에서 확인 가능하다
- 지원완료 탭의 카드에는 지원일을 표시한다
- 지원완료 탭에도 북마크·숨김 탭처럼 개수 배지를 둔다

## 검증 방법
### UI 수동
- 공고 탭에서 지원완료 버튼을 누르면 목록에서 바로 사라지고 지원완료 탭에 나타나는지 확인하기
- 북마크된 공고를 지원완료하면 북마크 탭에서도 사라지고, 해제하면 북마크 탭에 다시 나타나는지 확인하기
- 숨긴 공고를 지원완료하면 숨김 탭에서 빠지고, 해제하면 숨김 탭으로 돌아가며 공고 탭에는 나타나지 않는지 확인하기
- 상세에서 지원완료를 누르면 상세에 머무른 채 버튼이 활성 상태로 바뀌고, 목록으로 돌아가면 빠져 있는지 확인하기
- 지원완료 탭에서 해제하면 탭에서 빠지고 원래 탭으로 복귀하는지 확인하기
- 두 건 이상 지원했을 때 최근 지원이 위에 있고, 카드에 지원일이 보이는지 확인하기
- 지원완료 탭 배지 개수가 맞고, 지원 후 해당 회사의 관심회사를 해제해도 탭과 배지에 남는지 확인하기

### 자동 테스트
마감은 실제 사이트에서 공고가 내려가야 재현되므로 UI 수동 대신 자동 테스트로 확인한다. `test_api.py`의 `FakeScraper.data`에서 두 번째 실행 때 해당 공고를 빼서 마감을 만든다.
- `test_repository.py`
  - 지원완료 → 해제 → 재지원 (`created_at` 갱신), 이미 지원완료면 재지원해도 `created_at` 유지
  - 마감된 지원완료 공고가 `list_postings`·`get_posting`에 포함되고, 지원완료가 아닌 마감 공고는 제외
  - 마감됐던 공고가 다시 수집되면 `deleted_at`이 NULL로 돌아오고 지원완료는 유지
  - `delete_postings`가 `applications`도 지운다 (`test_delete_postings_removes_bookmark_hide_feedback` 확장)
- `test_jobs.py`: 재판정 exclude hard delete가 지원완료 공고와 `applications`까지 지운다 (`test_rejudged_exclude_hard_deletes_with_bookmark_and_feedback` 확장)
- `test_api.py`
  - `PUT` 반환 형식, 멱등, 없는 공고·마감 공고 404
  - `DELETE`는 마감 공고에도 200, 공고 행이 없으면 404
  - 스크래핑 2회로 마감을 만든 뒤 `/api/postings`에 `application`·`deleted_at`이 담겨 내려오는지. 그 공고에 피드백 생성이 200, 지원완료 아닌 마감 공고는 404
- `test_cli.py`
  - `postings`가 지원완료 공고를 제외
  - `posting <id>` 키 집합(`DETAIL_KEYS` + `application`), 마감 지원완료 공고는 반환·마감 비지원 공고는 `not_found`
  - readonly 0.4.0 DB에서 `postings --json`·`posting <id>`가 깨지지 않고 `application`이 null
- vitest (`App.test.tsx`·컴포넌트 테스트, `test/fixtures.ts`에 마감 공고 픽스처 추가)
  - 마감 지원완료 공고 카드에 "마감" 배지가 보이고 상세로 들어가진다
  - 마감 공고 해제 시 confirm이 뜨고, 취소하면 그대로 남는다. 확인하면 모든 탭에서 사라진다
  - 상세에 머문 채 마감 공고를 해제하면 상세는 유지되고 지원완료 버튼이 disabled
  - 마감 공고 카드·상세의 북마크·숨김 버튼이 disabled
  - 지원완료 탭은 관심회사가 아닌 회사의 공고도 포함

## 결정 사항 (2026-10-26)
- 상태 우선순위: 지원완료 > 숨김. 지원완료 공고는 숨김 여부와 무관하게 지원완료 탭에만 나온다. 숨김 탭에서도 제외
  - 지원완료 처리 시 북마크·숨김 상태는 건드리지 않는다. 해제하면 원래 상태(북마크/숨김)로 복귀
- 마감 처리: 북마크·숨김과 달리 지원완료는 이력이므로 공고가 soft delete돼도 지원완료 탭에 남긴다
  - 목록: `list_postings`의 삭제 조건을 `p.deleted_at IS NULL OR a.posting_id IS NOT NULL`로 바꾼다 (`include_deleted=False`일 때). 서버 응답 기준으로 삭제된 행은 지원완료 공고뿐이다
  - 프론트: 토글은 낙관적 업데이트라 재조회가 없다. 마감 공고를 해제하면 로컬 행이 `application: null, deleted_at != null`로 남아 다른 탭에 다시 나타나므로 `deleted_at == null || application != null` 필터를 둔다 (재조회 결과와도 일관)
    - 필터는 state가 아니라 `shown`처럼 파생값에 둔다. `PostingDetail`은 원본 `postings`를 받으므로, 상세에 머문 채 해제해도 행이 남아 아래의 disabled 버튼 상태가 가능하다 (state에서 지우면 상세가 "없음"이 된다)
    - 파생값은 두 갈래다. 공고·북마크·숨김 탭은 관심회사 필터 + 위 마감 필터 + `application == null`, 지원완료 탭은 `application != null`만 (관심회사 예외)
  - 상세: `get_posting`도 같은 조건으로 지원완료 공고는 삭제돼도 반환한다
  - 응답에 `deleted_at`을 포함한다 (`p.*`라 이미 내려가고 있음. 프론트 `Posting` 타입에 추가). 카드·상세에서 `deleted_at != null`이면 "마감" 배지
  - 상세의 지원 링크는 마감이어도 그대로 둔다 (외부 페이지가 이미 내려갔을 수 있음)
  - 마감된 공고는 새로 지원완료할 수 없고 해제만 가능하다. 해제하면 어느 탭에도 남지 않으므로 확인 다이얼로그를 띄운다 ("마감된 공고라 해제하면 다시 볼 수 없습니다"). `window.confirm`으로 충분하다. 모달 컴포넌트를 새로 만들지 않는다
  - 상세에 머문 채 해제하면 `deleted_at != null && application == null` 상태가 된다. 이때 지원완료 버튼은 disabled (PUT이 404이므로)
  - 마감 공고(`deleted_at != null`)는 카드·상세의 북마크·숨김 버튼도 disabled. `set_bookmark`·`set_hidden`이 활성 공고만 받아 404가 나므로, 마감 공고에서 가능한 조작은 지원완료 해제뿐이다
  - 예외: 피드백 생성(`POST /api/postings/{id}/feedback`)은 마감된 지원완료 공고에도 허용한다. `get_posting`을 거치므로 자연히 통과하고, 지원 후 면접 준비에 쓸모가 있다. 상세의 피드백 버튼도 그대로 둔다
- 관심회사 필터: 지원완료 탭은 관심회사 필터에서 예외다. 관심회사를 해제해도 지원 이력은 남는다
- 재판정에서 exclude로 바뀐 공고(`delete_postings` hard delete)는 기존 규칙대로 지원완료 상태여도 함께 지운다 (`applications` 포함)
  - 남기면 `breakdown NULL` 행이 계속 "다음 스크래핑 때 재판정"으로 보이고 "exclude는 저장하지 않는다" 규칙과 어긋난다. 대상은 0014 이전 행뿐이라 드물다
- 정렬: 지원완료 탭은 지원일 내림차순 (최근 지원이 위). 필터 없음
- 아이콘: 체크(check-circle). 활성 시 채워진 아이콘
- 구현: `applications(posting_id PK, stage TEXT, created_at, updated_at, deleted_at)` 테이블
  - `created_at` = 지원일, `deleted_at`은 사용자 해제에만 사용 (bookmarks·hides와 같은 규칙)
  - `stage`는 이번에는 항상 NULL (= 지원완료). 후속 spec에서 사용자가 입력한 단계 문자열을 넣는다. 고정 enum으로 두지 않는다
  - `updated_at`은 단계 변경 시각. 이번에는 `created_at`과 같다
  - 단계 이력(언제 어느 단계로 바뀌었는지)이 필요해지면 후속 spec에서 `application_events(posting_id, stage, created_at)`를 추가한다. 지원 시점은 `applications.created_at`으로 복원 가능하므로 지금 만들지 않는다
- API: 북마크·숨김의 boolean 토글과 달리 리소스로 둔다. 프론트도 `toggleFlag`와 별도 경로로 처리한다
  - `PUT /api/postings/{id}/application`: 지원완료. body 없음 (후속 spec에서 `{stage}`를 받아 단계 변경에도 쓴다)
    - 반환 `{posting_id, application: {applied_at, stage}}`
    - 이미 지원완료면 `created_at`을 유지한다 (멱등)
    - 공고가 없거나 마감이면 404 (북마크와 같음)
  - `DELETE /api/postings/{id}/application`: 해제. 마감 여부와 무관하게 200, 반환 `{posting_id, application: null}`. 공고 행 자체가 없으면 404
  - `/api/postings`·상세 응답에 `application: {applied_at, stage} | null` 포함. 프론트는 `application != null`로 지원완료를 판단한다
- CLI
  - `postings`는 지원완료 공고를 제외한다 (`include_hidden=False`와 같은 방식). 목록 키(`POSTING_KEYS`)에 `application`은 넣지 않는다 (항상 null이라 의미 없음)
  - `posting <id>`는 `application`을 포함한다 → `DETAIL_KEYS`·`plugin/skills/jobs/SKILL.md` 갱신
  - `posting <id>`의 `not_found`는 "없음, 또는 지원완료가 아닌 삭제 공고"로 바뀐다 → `plugin/skills/jobs/SKILL.md`·`backend/AGENTS.md`의 not_found 문구 갱신
  - readonly 옛 DB(0.4.0 등)에는 `applications` 테이블이 없다. 연결 시 `sqlite_master`로 테이블 유무를 확인하고, 없으면 JOIN 없이 `application`을 null로 채운다. 마감 공고 포함 조건도 적용하지 않는다
- 지원완료 탭 카드의 상태 표시 자리는 단계 라벨이 들어갈 수 있게 둔다 (이번에는 "지원완료" 고정)
- `just reset-db`는 DB 파일을 지우므로 지원 이력도 함께 삭제된다
