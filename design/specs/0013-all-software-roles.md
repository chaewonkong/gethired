# spec - 모든 소프트웨어 엔지니어 직군 지원
## 목표
- 백엔드뿐 아니라 프론트엔드·모바일·데이터·ML·인프라·보안·QA·임베디드·게임 클라이언트 등 모든 소프트웨어 엔지니어가 자기 이력서를 올리면 자기 직군 공고가 판정된다
- 판정의 역할 기준은 코드에 박힌 가정이 아니라 지원자 프로필에서 나온다
- 수집 범위가 특정 직군만 남기도록 좁혀진 스크래퍼를 소프트웨어 엔지니어링 전체로 넓힌다

## 목표가 아닌 것
- 디자이너·PM/PO·데이터 분석가 등 비개발 직군 지원. 판정에서 `exclude`로 유지
- exclude 판정 저장·열람 (별도 spec)
- 점수 배점을 사용자가 조정하는 기능
- 판정 프롬프트 외 UI 변경

## 기능
### 프로필: 직군 필드
- `Profile.roles: list[Role]`를 추가한다. `Role`은 아래 고정 어휘 중 하나. 경력에서 추론한 주력 직군 1~3개, 명시적 희망 역할이 아니라 "지금까지 해온 일" 기준. 희망 역할은 기존 `preferences.target_roles`에 그대로 둔다

| Role | 포함 |
|---|---|
| `backend` | 서버·API·플랫폼·게임 서버 |
| `frontend` | 웹 프론트엔드 |
| `fullstack` | 웹 프론트·백엔드 동시 |
| `ios` / `android` | 네이티브 모바일 |
| `cross-platform-mobile` | React Native·Flutter |
| `data-engineering` | 파이프라인·DW·데이터 플랫폼 |
| `data-science` | 모델링·분석 중심 (SQL·통계·실험) |
| `ml-engineering` | 학습·서빙·MLOps |
| `ml-research` | 연구·논문 |
| `infra-sre` | DevOps·SRE·클라우드·플랫폼 인프라 |
| `security-engineering` | 보안 엔지니어링 (정책·감사·개인정보 관리직 제외) |
| `qa` | QA·SDET·테스트 자동화 |
| `embedded` | 펌웨어·디바이스·커널 |
| `game-client` | 게임 클라이언트·엔진 |

- 추출 규칙: 이력서에 근거가 있는 직군만. 백엔드 경력자가 프론트를 조금 만졌다고 `frontend`를 넣지 않는다. 판단이 안 서면 빈 리스트
- `dealbreakers` 예시를 직군 중립("주니어 포지션", "특정 근무지")으로 바꾼다
- 하위 호환: `roles`는 기본값 `[]`. 이전 버전이 캐시한 프로필(roles 없음)은 그대로 로드되지만, 다음 스크래핑 때 재추출한다 (LLM 호출 1회)

### 판정 규칙
매처 SYSTEM 프롬프트를 아래 규칙으로 교체한다. 등급 구간(strong 80~100 · good 65~79 · stretch 45~64 · exclude 0~44)과 배점 합계는 유지한다.

1. **하드 불일치 (exclude)**
   - 소프트웨어 엔지니어링이 아닌 직군: 디자인, PM/PO/기획, 영업, 마케팅, HR, 재무·회계, CS, 법무, 정책·감사·개인정보 관리직, TPM·DevRel·테크니컬 라이터, 데이터 분석가
     - 예외: 데이터 분석가는 지원자 `roles`에 `data-science` 또는 `data-engineering`이 있으면 stretch까지 가능
   - 소프트웨어 엔지니어링이지만 지원자 `roles`와 겹치지도 인접하지도 않고 `core_skills`와도 겹치지 않는 직군 (예: 지원자 `frontend` ↔ 공고 `ml-research`)
2. **인접 직군 (exclude 금지, stretch 이상)**

표는 대칭이다. 지원자 직군에서 읽든 공고 직군에서 읽든 같은 쌍이 인접이다.

| 직군 | 인접 |
|---|---|
| backend | fullstack, data-engineering, ml-engineering, infra-sre, security-engineering, qa, embedded |
| frontend | fullstack, cross-platform-mobile, qa |
| fullstack | backend, frontend |
| ios | android, cross-platform-mobile, qa |
| android | ios, cross-platform-mobile, qa, embedded |
| cross-platform-mobile | ios, android, frontend |
| data-engineering | backend, ml-engineering, data-science |
| data-science | data-engineering, ml-engineering |
| ml-engineering | backend, data-engineering, data-science, ml-research |
| ml-research | ml-engineering |
| infra-sre | backend, security-engineering |
| security-engineering | backend, infra-sre |
| qa | backend, frontend, ios, android (자동화 스택이 맞는 쪽) |
| embedded | backend, android, game-client |
| game-client | embedded |

   - `roles`가 비어 있으면 `core_skills`·`domains`·`summary`로 직군을 추정해 같은 규칙을 적용한다
   - 인접이 아니어도 공고 필수 기술이 `core_skills`와 겹치면 exclude하지 않는다
3. **소프트 불일치**: 같은 직군 안에서 언어·프레임워크·연차가 다른 것. 등급을 한 단계 낮추되 제외하지 않는다. 도메인이 유사하면 언어가 달라도 good까지
4. **배점**: 핵심 기술 일치 35 · 도메인/업무 성격 일치 35 · 연차·시니어리티 일치 20 · 우대사항 일치 10. "핵심 기술"은 직군에 따라 언어·프레임워크·플랫폼·도구를 모두 포함한다. `preferences.target_roles`·`target_domains`와 맞는 공고는 우대사항 10점 안에서 가점하고, exclude 판단에는 쓰지 않는다
5. `gaps` 종류에 `role`을 추가한다 (예: `role: iOS 전담, 지원자는 웹 프론트엔드`). 기존 `language · framework · seniority · domain · other` 유지
6. `summary`·`tech_stack`·`fit_reason` 규칙은 기존 그대로

### 수집 범위
- 토스: `App`(iOS·Android), `Device`(디바이스 소프트웨어) 카테고리를 수집한다. `Technical Excellence`(DevRel·TPM·라이터)·`Data Analysis`·`Data Managing`·`Information Security`(정책·감사·개인정보)는 제외 유지
- 그 외 스크래퍼는 Tech/Engineering 부문 전체를 받고 있어 변경 없음. 열거형 필터를 쓰는 곳(두나무·카카오뱅크·래블업·크래프톤·현대·그리팅 계열)은 fixture 기준으로 프론트·모바일·ML·데이터·인프라·QA가 빠지지 않음을 확인했다
- 각 스크래퍼의 `expected_count`는 변경 시점의 실제 건수로 갱신한다

### 문서
- README 서비스 소개에 지원 직군 범위를 한 줄로 적는다. 플러그인 SKILL.md는 변경 없음

## 검증 방법
- pytest
  - 토스 fixture의 `App` 공고 2건이 `parse` 결과에 포함된다
  - `roles` 없는 캐시 dict가 `Profile.model_validate`를 통과하고, `get_profile`이 그 캐시를 쓰지 않고 재추출한다
  - `Profile` JSON 스키마에서 `roles.items`가 위 어휘의 enum이다
  - 데모 모드 골든 패스·기존 pytest·vitest 통과
- 수동 (provider 로그인, 저장된 토스·당근 공고로 `just match`)
  - 합성 이력서 3종(웹 프론트엔드 4년 · iOS 5년 · ML 엔지니어 3년)으로 각각 판정했을 때, 같은 직군 공고 중 exclude가 0건이고 디자인·PO 공고는 전부 exclude
  - 같은 이력서의 프로필 캐시에서 `roles`를 비운 뒤 다시 판정해도 같은 직군 공고의 exclude가 0건 (규칙 2의 추정 분기)
  - `scripts/match.py --planted`: 백엔드 이력서로 `planted-fit` strong, `planted-unfit-ios`·`planted-unfit-sales` exclude
  - 백엔드(실제) 이력서로 판정했을 때 기존 판정과 등급 분포가 크게 다르지 않다 (strong·good 건수 기준)
  - 프론트엔드 이력서로 백엔드 공고는 대부분 exclude 또는 stretch, 풀스택·RN 공고는 stretch 이상

## 결정 사항 (2026-10-20)
- 직군은 자유 텍스트가 아닌 고정 어휘(enum). 프롬프트의 인접 표와 1:1로 맞추기 위해서이고, LLM이 "Platform Engineer" 같은 표현을 임의로 만들면 표가 무력화된다
- `roles`는 `preferences.target_roles`와 분리한다. 전자는 "해온 일", 후자는 "하고 싶은 일". 판정의 exclude 기준은 전자, 희망은 우대사항 10점 안의 가점에만 쓴다
- 인접 표는 대칭으로 둔다. 비대칭이면 LLM이 지원자·공고 어느 쪽에서 읽느냐에 따라 결과가 갈린다
- 컬리 `보안` 직군은 수집하지 않는다. fixture 4건이 전부 개인정보보호·정보보호 정책·보안 솔루션 운영 담당자로 소프트웨어 엔지니어링이 아니고, 수집하면 매 스크래핑마다 exclude용 LLM 비용만 든다
- 캐시 프로필에 `roles`가 없으면 재추출한다. 호출 1회 비용이고, 직군 앵커 없이 판정하면 이 spec의 목적이 무너진다. 필드 유무로 무효화하는 방식은 이번 한 번용이고, 다음 프로필 스키마 변경 때 `profile_cache`에 `schema_version` 도입을 검토한다 (범위 밖)
- 데이터 분석가·정책성 보안직은 소프트웨어 엔지니어링으로 보지 않는다. 이력서가 SQL·통계 중심이면 `data-science`로 흡수한다
- 인접 표는 프롬프트 문자열이 아니라 코드 데이터(`ADJACENT`)로 두고 프롬프트를 거기서 렌더링한다. 완전성·대칭을 테스트로 고정하기 위해서다
- enum 밖 role 값 대비 테스트는 넣지 않는다. 두 provider 모두 스키마로 enum을 강제하고, 그래도 어긋나면 `jobs.py`가 ValidationError로 job을 실패 처리한다
- exclude 저장(감사)은 범위 밖. 이 spec만으로도 오탐 확인은 합성 이력서 수동 검증으로 한다
- 구체 작업 순서·파일 단위 계획·테스트 항목은 `design/plans/plan-0013.md`
