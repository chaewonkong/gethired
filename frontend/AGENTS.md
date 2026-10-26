# frontend

React 19 + Vite 6 + TypeScript + react-router-dom 7. 상태 관리 라이브러리 없이 `App.tsx`가 상태를 들고 라우트(탭·상세) 컴포넌트에 내려준다. `main.tsx`가 `<BrowserRouter>`로 감싼다.
백엔드 API는 `/api` (dev에서는 Vite가 8000으로 프록시, `just run`에서는 백엔드가 `backend/app/static/`을 정적 서빙하고 클라이언트 경로는 `index.html`로 fallback).

## 라우팅
| 경로 | 화면 |
|---|---|
| `/` | 공고 탭 (`PostingsTab`) |
| `/bookmarks` | 북마크 탭 |
| `/applied` | 지원완료 탭 (`AppliedTab`) |
| `/hidden` | 숨김 탭 |
| `/companies` | 회사 탭 |
| `/postings/:id` | 공고 상세 (`PostingDetail`) |
| `*` | `<Navigate to="/" replace>` |

- 탭 버튼은 `navigate(path)`, `aria-selected`는 현재 경로로 (상세에서는 탭이 보이되 선택 없음). 관심회사 저장 후 `/`. 온보딩 분기는 경로와 무관하게 `App` 상단에서 처리
- 목록 위치 복원: 카드 클릭 **직전**에 `saveListPosition(path, {scrollY, visible})`로 sessionStorage에 저장(unmount 때 읽으면 DOM이 바뀐 뒤라 0). 복원은 `useNavigationType() === "POP"`(뒤로가기)일 때만, `visible`을 먼저 복원하고 렌더 뒤 `scrollTo`. 탭 버튼으로 돌아오면 맨 위, 상세 진입도 맨 위. 필터는 원래 `useSessionState`라 유지
- 상세의 "목록으로": `location.key === "default"`(URL 직접 진입)면 `navigate("/")`, 아니면 `navigate(-1)`

## 명령 (frontend/에서)
```bash
npm run dev     # 5173, /api → localhost:8000
npm run build   # tsc -b && vite build → ../backend/app/static/ (휠에 포함)
npm test        # vitest run (jsdom, src/**/*.test.*)
npm run typecheck && npm run lint  # tsc --noEmit + eslint (eslint.config.js, CI ci-frontend.yml과 동일)
npm run test:e2e  # Playwright chromium 프로젝트 (build 선행, sandbox 밖). 최초 1회 just e2e-install
E2E_DEMO=1 npm run demo:record  # demo 프로젝트: 데모 모드 백엔드 위에서 골든 패스 녹화 (루트: just screenshots)
```
sandbox에서 npm 설치는 `npm_config_cache=../.npm-cache`를 붙인다 (홈 캐시 쓰기 불가).

## 컴포넌트
| 파일 | 역할 |
|---|---|
| `src/api.ts` | 타입(`Posting`, `Company`, `Job`, `ProviderSetting`, `AuthStatus` …)과 fetch 래퍼 `api`. 스크래핑 401은 `LoginRequiredError`(`provider`, `message`), provider 변경·스크래핑 시작 409는 `JobRunningError`, 이력서 업로드 400은 `ResumeRejectedError`(message = 서버 detail). 상세 404는 `NotFoundError`, 피드백 생성 401·409는 위 둘을 그대로 쓰고 502·400(`llm_error`·`no_resume`)은 `LlmError`(message). `api.posting(id)`·`api.generateFeedback(id)`, 타입 `PostingDetail`·`Breakdown`·`Feedback`·`Requirement`(`{text, fit: FitMark | null}`, `Posting.breakdown`은 nullable). `Posting.application: Application | null`(`{applied_at, stage}`, spec 0015)·`Posting.deleted_at: string | null`(마감. 지원완료 공고만 마감된 채 내려온다). `api.setApplied(id)`는 PUT 응답의 `application`을 돌려주고 `api.clearApplied(id)`는 DELETE. `putResume`는 파일 바이트를 그대로 PUT |
| `src/App.tsx` | 최상위 상태: postings, companies, resume 파일, provider 설정(`setting`)·로그인 상태(`auth`), 진행 중 job(1.5초 폴링), 로그인/에러 배너, toast, 경로 ↔ 탭 매핑과 `<Routes>`. auth 폴링은 AI 선택 화면·AI 모달·로그인 배너가 보일 때만, 응답 후 3초 setTimeout 체인. 화면 단계(`phase`) 계산. 관심회사 기준으로 공고를 걸러 탭에 전달. 북마크·숨김 토글(`toggleFlag`: 낙관적 업데이트, 실패 시 롤백, 요청 중 중복 토글 무시. 저장되면 `true`, 롤백·중복이면 `false`를 반환해 목록에 없는 공고의 상세가 자기 복사본을 갱신할 수 있게 한다), 관심회사 별 토글도 같은 방식. 지원완료 토글(`toggleApplied`)은 리소스라 별도 함수: 켜기는 낙관적 값을 넣고 PUT 응답의 `application`으로 교체, 끄기는 마감 공고면 `window.confirm` 후 DELETE, 실패 시 롤백. 파생값은 두 갈래: `live`(마감 공고는 지원완료인 것만. 해제 직후 로컬 행이 다른 탭에 새지 않게) → `shown`(관심회사 + `application == null`, 공고·북마크·숨김 탭과 배지)과 `applied`(`application != null`만, 관심회사 예외, `Date.parse(applied_at)` 내림차순·동률 id 내림차순). `PostingDetail`에는 관심회사 필터 전 `postings` 전체를 넘긴다 (낙관적 업데이트가 거기에 반영됨) |
| `components/PostingsTab.tsx` | 공고 탭: 스크래핑 버튼, 회사·등급 필터(sessionStorage 유지), 숨긴 공고 제외, 정렬(적합도·최신·오래된순, 최신은 `first_seen_at` 기준, 동률은 score), infinite scroll(20건, `IntersectionObserver`), 스크래핑 진행·완료 요약. `formatTime` export |
| `components/CompanyFilter.tsx` | 회사 Multi-select 드롭다운: 전체 켜기/끄기, 회사별 공고 수, 바깥 클릭·Esc로 닫힘. 선택은 "해제한 회사 목록"으로 다룸 |
| `components/BookmarksTab.tsx` | 북마크 탭: `bookmarked`이고 숨기지 않은 공고만 score순. 해제 시 즉시 빠짐 |
| `components/AppliedTab.tsx` | 지원완료 탭: App이 지원일 내림차순으로 정렬한 `applied`를 그대로 렌더. 해제 시 원래 탭(북마크/숨김/공고)으로 복귀, 마감 공고면 어디에도 남지 않음 |
| `components/HiddenTab.tsx` | 숨김 탭: `hidden` 공고만 score순. 해제 시 공고 탭으로 복귀 |
| `components/CompaniesTab.tsx` | 회사 탭: 관심회사 별 토글, 채용 사이트 링크, 마지막 스크래핑 결과·시각 |
| `components/ResumeDropzone.tsx` | 이력서 드래그앤드롭·클릭 업로드 영역(여러 파일). `invalidResumeFiles`: `.md`·`.pdf` 확장자 검증, 크기 제한 없음 |
| `components/CompanySelect.tsx` | 온보딩 관심회사 선택: 초기 전부 해제, 0개 확인은 `onEmpty` |
| `components/ProviderPicker.tsx` | Claude Code / Codex 카드(radiogroup). 선택 카드에 로그인 배지 3상태(확인 중 / 로그인됨 / 로그인 필요 + 명령). `disabled`면 안내만. 화살표 이동, Enter/Space 선택. `PROVIDERS`, `PROVIDER_NAME` export |
| `components/ProviderSelect.tsx` | 온보딩 AI 선택: 카드 선택 시 PUT, "계속"은 미저장이면 PUT 후 진행. 로그인 여부 무관 |
| `components/ProviderModal.tsx` | 헤더 "AI" 버튼·배너 "AI 변경"의 모달. 선택 즉시 PUT, 스크래핑 중 disabled. Esc·바깥 클릭 닫힘 |
| `components/ResumeModal.tsx` | 헤더 "이력서" 버튼의 관리 창: 파일 목록·삭제·업로드. Esc·바깥 클릭으로 닫힘 |
| `components/Toast.tsx` | 하단 toast. `TOAST_MS`(2초) 뒤 자동으로 `onClose` |
| `components/PostingCard.tsx` | 공고 카드: 등급·점수, 마감 D-day(7일 이내 강조), 기술 스택, gaps, 추천 이유, 북마크 별, 숨김(눈) 버튼, 지원 링크. 카드·제목 클릭(`role="link"`, `tabIndex=0`, `aria-label`=제목, Enter)은 위치 저장 후 `/postings/:id`. 별·숨김·지원 링크는 `stopPropagation`으로 이동하지 않음. `visible`은 선택 prop(`PostingsTab`만 넘김, 위치 저장용). 지원완료(체크) 버튼 `AppliedButton`(활성 시 채움). 마감(`deleted_at != null`)이면 `Deadline`이 D-day 대신 "마감" 배지(`closed` prop), 별·숨김은 disabled(서버가 404), 체크는 `application == null`일 때만 disabled(해제만 가능). `application`이 있으면 하단에 `stage ?? "지원완료"` · 지원일(로컬 날짜). `Deadline`·`StarButton`·`HideButton`·`AppliedButton` export (상세가 재사용) |
| `components/PostingDetail.tsx` | 공고 상세: mount 시 `api.posting(id)` 직접 fetch. 헤더(회사·제목·등급·점수·마감·지원·북마크/숨김) · 공고(summary·tech_stack, 맨 아래 접힌 본문 `<details>`, description null이면 생략) · 정합성(`FitTable` 자격요건·우대사항 표: 항목마다 ✓ 초록(met) / △ 주황(partial) / ✗ 빨강(unmet), fit null은 회색 –, `aria-label`은 충족/부분 충족/미충족/판정 없음 · `BreakdownBars` 4축 `n/max` 막대, breakdown null이면 "다음 스크래핑 때 재판정" 안내 · fit_reason · gaps) · 피드백. props: `postings`, `byId`, `loginRequired: boolean`, `onToggleBookmark`/`onToggleHidden`/`onToggleApplied: (p) => Promise<boolean>`, `onRequireLogin(message)`, `onToast(text, kind)`. 북마크·숨김·지원완료 상태는 App `postings`에서 id로 읽고, 없으면(직접 진입·관심회사 아님) 상세 응답을 `Posting`으로 넘겨 토글하고 `true`면 자기 복사본 갱신. 마감 배지·버튼 disabled 규칙은 카드와 같다. 지원 링크·피드백 생성은 마감이어도 그대로. `BreakdownBars` export, 막대는 `role="meter"` + `aria-label`(핵심 기술 / 도메인·업무 / 연차 / 우대사항). 피드백: null → "피드백 생성" 버튼(로그인 선확인 없음) / 생성 중 비활성 + 스피너 / `current` → 목록 / `!current` → "이전 이력서 기준 피드백" 접힘 + 버튼 / 401 → 버튼 자리에 로그인 안내(상세가 401을 봤고 App `loginRequired`도 켜져 있을 때만. 해제되면 버튼 복귀) / 409·`LlmError`·그 외 오류 → toast. 404면 "공고를 찾을 수 없습니다" + `/` 링크 |
| `components/ScrapeProgress.tsx` | 스크래핑 중 회사별 상태 점 |
| `components/ScrollTopButton.tsx` | 600px 이상 스크롤 시 나타나는 맨 위로 버튼 |
| `components/Logo.tsx` | 헤더 로고 |
| `src/sessionState.ts` | `useSessionState`: sessionStorage에 유지되는 state. 접근·파싱 실패 시 기본값. `saveListPosition(path, {scrollY, visible})`(키 `listPosition:<path>`)·`useListPosition(path, ready)`: POP 진입일 때만 저장값을 돌려주고 `ready`(목록에 항목 있음)가 되면 한 번 스크롤. 그 외 진입은 맨 위. `PostingsTab`은 이전 필터 값을 `useRef`에 들고 실제로 바뀔 때만 `visible`을 리셋한다 |
| `src/styles.css` | 전역 스타일. 색은 `:root` 변수. 모바일 우선, 480/640px 브레이크포인트, 최대 폭 800px |

## 규칙
- 데이터는 `App`에서만 fetch한다. 탭·카드는 props와 콜백만 받는다. 예외: `PostingDetail`은 라우트 단위 데이터라 상세·피드백을 직접 fetch한다 (spec 0014)
- 이력서 업로드 중 서버가 400으로 거부한 파일은 toast로 알리고 나머지는 계속 올린다. 전부 성공일 때만 성공 toast·`holdUpload`
- 화면 단계는 상태에서 계산한다: `resumeFiles`·`setting` 로드 전 → loading, resume 파일 없음 → upload, `!setting.chosen` → provider, 관심회사 없음 → select, 그 외 main. 첫 화면은 `/api/auth/status`(CLI 실행)를 기다리지 않는다. 온보딩 업로드 직후에만 toast가 닫힐 때까지 upload에 머문다 (`holdUpload`)
- 스크래핑 시작이 409(다른 프로세스, 예: CLI `scrape`가 락 보유)면 "다른 곳에서 스크래핑 중입니다" error toast, job 폴링은 시작하지 않는다
- 관심회사가 아닌 회사의 공고는 `App`에서 걸러 모든 탭·배지에서 뺀다. 예외: 지원완료 탭은 이력이라 관심회사를 해제해도 남는다
- 상태 우선순위는 지원완료 > 숨김 > 북마크. 지원완료 공고는 공고·북마크·숨김 탭과 배지에서 빠지고, 해제하면 원래 상태로 돌아간다
- 날짜 `YYYY-MM-DD`는 로컬 자정으로 해석한다 (`new Date(s)`는 UTC로 읽어 KST에서 하루 밀림)
- UI: 흰 배경, 하늘색 포인트, 카드 1열
- 주석은 최소한으로

## 테스트
- Vitest 5 + Testing Library + jsdom. 설정은 `vite.config.ts`의 `test`, `src/test/setup.ts`
- 테스트는 `TZ=Asia/Seoul`로 돈다 (`vite.config.ts`)
- 픽스처: `src/test/fixtures.ts`의 `makePosting`(`breakdown: null`, `application: null`, `deleted_at: null`), `makeDetail`, `makeCompany`, `stubIntersectionObserver`. `setup.ts`가 `window.scrollTo`를 stub (jsdom 미구현)
- `App`은 `src/test/renderApp.tsx`의 `renderApp(path)`(`MemoryRouter initialEntries=[path]`)으로, `useNavigate`·`useParams`를 쓰는 컴포넌트(`PostingCard`와 그걸 쓰는 탭들, `PostingDetail`)는 `renderInRouter(ui, {entries, route})`로 렌더한다. `route`를 주면 `<Route path={route}>` 아래에 렌더해 `useParams`가 동작하고, `location()`과 같은 Router 안의 `rerender`를 돌려준다. Router 밖에서 직접 렌더하면 `useNavigate`가 깨진다
- 네트워크는 `vi.stubGlobal("fetch", …)`로 대체. 테스트 파일은 대상 옆에 `*.test.ts(x)`
- 온보딩·이력서 관리·AI 선택 흐름은 `src/Onboarding.test.tsx`의 `stubBackend`(resume·관심회사·provider·로그인 상태를 가진 가짜 백엔드, 두 번째 인자 `routes`로 경로별 응답 override)로 검증
- e2e: `e2e/README.md`. 실제 FastAPI + 빌드된 static + chromium. `e2e/fake-bin`의 가짜 `claude`/`codex`가 `FAKE_AUTH_FILE`로 로그인 상태를 흉내 낸다. vitest가 집어 들지 않도록 `*.spec.ts`
- Playwright 프로젝트 둘: `chromium`(테스트, `demo.spec.ts` 제외)과 `demo`(`demo.spec.ts`만, 1000×720 · 1x · Asia/Seoul · ko-KR · video on). `test:e2e`는 `--project chromium`이라 녹화를 돌리지 않는다. `server.sh`는 `E2E_DEMO=1`이면 `--demo`로 백엔드를 띄운다. `make-gif.sh`가 webm → GIF (5MB 초과 시 실패)
