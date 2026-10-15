# frontend

React 19 + Vite 6 + TypeScript. 상태 관리·라우팅 라이브러리 없이 `App.tsx`가 상태를 들고 탭 컴포넌트에 내려준다.
백엔드 API는 `/api` (dev에서는 Vite가 8000으로 프록시, `just run`에서는 백엔드가 `dist/`를 정적 서빙).

## 명령 (frontend/에서)
```bash
npm run dev     # 5173, /api → localhost:8000
npm run build   # tsc -b && vite build → dist/
npm test        # vitest run (jsdom)
```
sandbox에서 npm 설치는 `npm_config_cache=../.npm-cache`를 붙인다 (홈 캐시 쓰기 불가).

## 컴포넌트
| 파일 | 역할 |
|---|---|
| `src/api.ts` | 타입(`Posting`, `Company`, `Job` …)과 fetch 래퍼 `api`. 스크래핑 401은 `LoginRequiredError` |
| `src/App.tsx` | 최상위 상태: postings, companies, resume 파일, 진행 중 job(1.5초 폴링), 로그인/에러 배너, toast, 탭 전환. 화면 단계(`phase`) 계산. 관심회사 기준으로 공고를 걸러 탭에 전달. 북마크·숨김 토글(`toggleFlag`: 낙관적 업데이트, 실패 시 롤백, 요청 중 중복 토글 무시), 관심회사 별 토글도 같은 방식 |
| `components/PostingsTab.tsx` | 공고 탭: 스크래핑 버튼, 회사·등급 필터(sessionStorage 유지), 숨긴 공고 제외, score 정렬, infinite scroll(20건, `IntersectionObserver`), 스크래핑 진행·완료 요약. `formatTime` export |
| `components/CompanyFilter.tsx` | 회사 Multi-select 드롭다운: 전체 켜기/끄기, 회사별 공고 수, 바깥 클릭·Esc로 닫힘. 선택은 "해제한 회사 목록"으로 다룸 |
| `components/BookmarksTab.tsx` | 북마크 탭: `bookmarked`이고 숨기지 않은 공고만 score순. 해제 시 즉시 빠짐 |
| `components/HiddenTab.tsx` | 숨김 탭: `hidden` 공고만 score순. 해제 시 공고 탭으로 복귀 |
| `components/CompaniesTab.tsx` | 회사 탭: 관심회사 별 토글, 채용 사이트 링크, 마지막 스크래핑 결과·시각 |
| `components/ResumeDropzone.tsx` | 이력서 드래그앤드롭·클릭 업로드 영역(여러 파일). `invalidResumeFiles`: `.md`·1MB 검증 |
| `components/CompanySelect.tsx` | 온보딩 관심회사 선택: 초기 전부 해제, 0개 확인은 `onEmpty` |
| `components/ResumeModal.tsx` | 헤더 "이력서" 버튼의 관리 창: 파일 목록·삭제·업로드. Esc·바깥 클릭으로 닫힘 |
| `components/Toast.tsx` | 하단 toast. `TOAST_MS`(2초) 뒤 자동으로 `onClose` |
| `components/PostingCard.tsx` | 공고 카드: 등급·점수, 마감 D-day(7일 이내 강조), 기술 스택, gaps, 추천 이유, 북마크 별, 숨김(눈) 버튼, 지원 링크 |
| `components/ScrapeProgress.tsx` | 스크래핑 중 회사별 상태 점 |
| `components/ScrollTopButton.tsx` | 600px 이상 스크롤 시 나타나는 맨 위로 버튼 |
| `components/Logo.tsx` | 헤더 로고 |
| `src/sessionState.ts` | `useSessionState`: sessionStorage에 유지되는 state. 접근·파싱 실패 시 기본값 |
| `src/styles.css` | 전역 스타일. 색은 `:root` 변수. 모바일 우선, 480/640px 브레이크포인트, 최대 폭 800px |

## 규칙
- 데이터는 `App`에서만 fetch한다. 탭·카드는 props와 콜백만 받는다
- 화면 단계는 상태에서 계산한다: resume 파일 없음 → upload, 관심회사 없음 → select, 그 외 → main. 온보딩 업로드 직후에만 toast가 닫힐 때까지 upload에 머문다 (`holdUpload`)
- 관심회사가 아닌 회사의 공고는 `App`에서 걸러 모든 탭·배지에서 뺀다
- 날짜 `YYYY-MM-DD`는 로컬 자정으로 해석한다 (`new Date(s)`는 UTC로 읽어 KST에서 하루 밀림)
- UI: 흰 배경, 하늘색 포인트, 카드 1열
- 주석은 최소한으로

## 테스트
- Vitest 5 + Testing Library + jsdom. 설정은 `vite.config.ts`의 `test`, `src/test/setup.ts`
- 테스트는 `TZ=Asia/Seoul`로 돈다 (`vite.config.ts`)
- 픽스처: `src/test/fixtures.ts`의 `makePosting`, `makeCompany`, `stubIntersectionObserver`
- 네트워크는 `vi.stubGlobal("fetch", …)`로 대체. 테스트 파일은 대상 옆에 `*.test.ts(x)`
- 온보딩·이력서 관리 흐름은 `src/Onboarding.test.tsx`의 `stubBackend`(resume·관심회사 상태를 가진 가짜 백엔드)로 검증
