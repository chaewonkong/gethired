# spec - codex 지원 · 하네스 선택
## 목표
- Claude Code 외에 Codex CLI 구독 세션으로도 프로필 추출·판정을 할 수 있다
- API key는 쓰지 않는다 (기존 규칙 유지)
- 사용자가 하네스(Claude Code / Codex)를 UI에서 고르고, 고른 하네스의 로그인 여부를 바로 확인한다

## 목표가 아닌 것
- 모델 선택 UI. 이번엔 기본값 + env override까지만, 추후 UI
- 로그인 자체를 UI에서 처리하는 것. 두 CLI 모두 터미널 device flow라 안내와 상태 확인만 한다
- 하네스 전환 시 기존 판정·프로필 캐시 무효화

## 용어
- provider = 하네스. `claude` | `codex`

## 기능
- 온보딩에 "AI 선택" 단계가 추가된다. 순서는 이력서 업로드 → AI 선택 → 관심회사 선택. 빠진 단계만 진행한다 (0005 규칙)
  - Claude Code / Codex 카드 중 하나를 고른다. 고르면 저장되고, 그 provider의 로그인 상태가 카드에 배지로 표시된다
  - 미로그인이면 배지에 터미널에서 실행할 로그인 명령이 보이고, 사용자가 터미널에서 로그인하면 새로고침 없이 배지가 "로그인됨"으로 바뀐다
  - 로그인 여부와 무관하게 "계속"으로 다음 단계로 갈 수 있다
- 온보딩 이후에는 헤더 "AI" 버튼으로 같은 선택 화면을 모달로 열어 provider를 바꿀 수 있다
- 스크래핑 실행 중에는 provider를 바꿀 수 없다. 모달은 안내 문구만 보인다
- 스크래핑 시 provider가 미로그인이면 배너에 해당 provider의 로그인 명령이 보인다. 배너에서 "AI 변경"으로 모달을 열 수 있고, 로그인하면 배너가 사라진다
- 프로필 추출·판정은 선택된 provider로 실행된다. `just match`도 provider를 따른다
- codex로 실행한 job은 비용이 표시되지 않는다 (구독 세션, 비용 산출 불가)

## 검증 방법
- 최초 진입 → 업로드 → AI 선택 화면. 카드 2개, 기본 선택은 Claude Code
- codex 카드 선택 → 미로그인이면 "로그인 필요 · `codex login`" 배지 → 터미널에서 로그인 → 새로고침 없이 "로그인됨"
- 미로그인 상태에서 "계속" → 관심회사 선택 → 메인. 새로고침해도 AI 선택 화면으로 돌아가지 않는다
- 이력서·관심회사가 이미 있고 provider만 없으면 AI 선택 화면부터 시작한다
- 메인에서 "AI" 버튼 → 모달 → 다른 provider로 전환 → 닫고 다시 열면 유지된다
- 스크래핑 중 모달을 열면 전환 불가 안내가 보이고 카드를 눌러도 바뀌지 않는다
- 미로그인 provider로 "스크래핑 하기" → 배너에 그 provider의 로그인 명령 → 로그인하면 배너가 사라진다
- codex로 스크래핑하면 기존과 같은 결과(공고·등급)가 저장되고, 비용 표시는 없다
- `LLM_PROVIDER=codex`로 띄우고 아직 선택하지 않았으면 AI 선택 화면에서 Codex가 미리 선택돼 있다
- `CLAUDE_MODEL`, `CODEX_MODEL` env로 모델이 바뀐다
- 첫 화면은 CLI 응답을 기다리지 않고 바로 그려진다
- 키보드만으로 provider 선택과 "계속"이 가능하다

## 결정 사항 (2026-10-17)
- provider는 DB에 저장하고 UI에서 바꾼다. 저장값이 없으면 "미선택"이며 `LLM_PROVIDER` env는 미선택 상태의 기본 선택값으로만 쓴다 (Docker에서 기본값 주는 경로)
- 기존 사용자(이력서·관심회사 있음)도 업그레이드 후 AI 선택 화면을 한 번 본다
- 전환은 job 실행 중에는 불가. job 시작 시점의 provider로 job 전체가 고정된다
- 모델은 `CLAUDE_MODEL`(기본 `claude-opus-5-5`), `CODEX_MODEL`(미설정이면 codex 기본 모델)
- codex 바이너리 위치는 `CODEX_BIN` env (기본 `codex`)
- 설정 조회와 로그인 확인은 분리한다. 첫 화면은 DB만 보고 그리고, CLI 결과는 늦게 채운다
- 로그인 확인은 provider별 CLI(`claude auth status` / `codex login status`)로 하고, 미로그인 `codex exec`는 스스로 끝나지 않으므로 호출 전에 반드시 확인한다
- codex는 `cost_usd=0`. 토큰 수만 기록한다
- `profile_cache`는 이력서 해시가 키. provider 전환 시 비우지 않는다
- "API key 안 씀"은 codex에서는 안내다. `codex login --with-api-key`로 로그인한 세션은 막을 수 없다
- 실행 계획과 CLI 실측은 `design/plans/plan-0008.md`
