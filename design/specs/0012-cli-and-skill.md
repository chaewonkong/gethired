# spec - 헤드리스 CLI + 에이전트 스킬
## 목표
- 브라우저 없이 `gethired` CLI만으로 온보딩 → 스크래핑 → 공고 조회가 된다. 출력은 에이전트가 읽을 수 있는 JSON
- Claude Code 플러그인(스킬)으로 설치하면, "나한테 맞는 공고 있어?" 같은 요청에 에이전트가 CLI로 상태·공고를 읽어 요약한다

## 목표가 아닌 것
- 주기 실행·push 알림 (`autopilot`). 다음 spec
- 스킬이 `scrape`를 직접 실행하는 것
- MCP 서버
- 판정 LLM을 에이전트 자신으로 바꾸는 것. provider CLI 세션 호출은 그대로
- 웹 UI 기능 변경. 아래 "409 토스트" 한 가지만 예외

## 기능
### CLI (`gethired <command> [--json]`)
| 명령 | 동작 |
|---|---|
| `status` | 이력서 수, provider(DB 설정만), 관심회사, 회사별 마지막 성공 실행, `stale`(관심회사 중 하나라도 마지막 성공 실행이 24h 초과 또는 없음), `job_running` |
| `resume add <file...>` / `resume list` / `resume rm <name>` | 이력서 복사 등록(같은 이름 덮어쓰기)·목록·삭제. `resume.py`와 같은 검증 |
| `provider [claude\|codex]` | 인자 없으면 DB 설정 출력, 있으면 저장 |
| `companies` | 등록 회사 + 관심 여부 + 마지막 실행 |
| `interest add\|rm <company...>` | 관심회사 설정 |
| `scrape [company...]` | 관심회사(또는 지정 회사) 스크래핑·판정을 동기 실행. 진행은 stderr로 회사별 출력. 결과는 `/api/scrape/{id}`와 같은 필드 + `failed: [{company, error}]` |
| `postings [--min-level good] [--company ...] [--since 24h] [--limit N] [--full]` | 저장된 공고. 숨김 제외·관심회사만·score 내림차순. `--min-level`은 API와 같은 "이상". `--since`는 `scraped_at`(처음 저장된 시각) 기준. 기본 필드 `id company title fit_level score fit_reason apply_url deadline scraped_at`, `summary`·`gaps`는 `--full` (공고 본문 컬럼은 없음) |

- `--json`은 서브커맨드별 플래그. stdout에는 JSON만, 로그·진행은 stderr. 필드 이름은 기존 API 응답과 같다
- 읽기 명령(`status`·`companies`·`postings`·`resume list`·`provider` 조회)은 DB를 `mode=ro`로 열고 스키마를 만들지 않는다. DB가 없으면 `status`·`postings`는 "온보딩 안 됨", `companies`·`provider` 조회는 기본값(온보딩에 필요)
- exit code

| exit | 경우 |
|---|---|
| 0 | 성공. 일부 회사 실패는 `failed`에 담고 stderr 경고 |
| 1 | 전체 실패(프로필 추출 실패·모든 회사 실패)·`job_running`·입력 오류·텍스트 없는 PDF |
| 3 | 로그인 필요 (선체크 또는 도중 `auth_required`. 부분 결과 `job` 포함) |
| 130 | Ctrl+C 중단. `job.status`는 `interrupted`, 락 해제, 진행 중 run은 실패로 마감 |

- exit≠0이면 JSON은 `{code, message, login_command?, job?}`. API 401에도 `login_command`를 추가해 이름을 맞춘다
- CLI 진입점도 `main.py`처럼 `ANTHROPIC_API_KEY`·`OPENAI_API_KEY`를 제거한다
- 기존 `serve`·`auth`·`reset-db`·`paths` 유지

### 공용 코드
- `JobManager.prepare()`(선체크)·`start()`(락 획득 + job 생성, 동기)·`run()`(`start` 후 완료까지 대기) 공개 API. UI는 `start`, CLI는 `run`
- 로그인 선체크·관심회사 0개 검사를 `api.py`에서 `JobManager`로 옮긴다. 타입 있는 예외 → API 401/400, CLI exit 3/1
- `repository.list_postings`에 숨김 제외·관심회사만 옵션 추가. 기본값은 현행, 프론트는 그대로
- 프로세스 간 배타: `filelock`(Unix `flock`, Windows `msvcrt.locking` — Windows는 미검증)으로 `DB_PATH` 옆 `app.lock`(같은 DB를 쓰는 프로세스끼리 배타). 락은 job 생성과 함께 동기로 잡아 `POST /scrape` 202 시점에 보유가 보장된다. UI job 시작·CLI `scrape`·provider 변경이 공통으로 잡는다. 보유 중이면 API 409 / CLI exit 1 `job_running`. 프로세스가 죽으면 OS가 해제
- UI: 스크래핑 시작이 409면 "다른 곳에서 실행 중" 토스트

### 데모 모드
- `GETHIRED_DEMO=1`은 CLI에도 적용: 데모 스크래퍼·고정 판정·`logged_in` True·고정 시각을 같은 팩토리로 주입. `DB_PATH`·`RESUME_DIR`이 없으면 exit 1로 지정을 요구한다 (프로세스마다 DB가 달라지는 사고 방지)

### 플러그인
- 저장소 루트 `.claude-plugin/marketplace.json` + `plugin/`(`.claude-plugin/plugin.json`, `skills/jobs/SKILL.md`). 설치: `claude plugin marketplace add chaewonkong/gethired` → `claude plugin install gethired@gethired`. 호출명 `/gethired:jobs`, 설명으로 자동 발동
- 스킬은 `uvx --from gethired~=0.2.0 gethired <cmd> --json`으로 읽기 명령만 실행한다 (`status`·`postings`·`companies`). sandbox에 막히면(uv 캐시·PyPI) 스킬이 따로 묻지 않고 에이전트의 기본 권한 절차(sandbox 밖 재실행 승인)에 맡긴다. README에 `Bash(uvx --from gethired~=0.2.0 gethired *)` 허용을 1순위로, sandbox `allowWrite`·`allowedDomains`는 대안(uv 캐시를 모든 sandbox 명령에 여는 위험 명시)으로 안내. 버전 범위는 `~=0.2.0`(= `>=0.2.0,<0.3`)으로 써서 따옴표·`<>` 없이 권한 규칙과 정확히 매칭
- 절차: 트리거(구직·공고·이직·이력서 매칭) → `status` → 온보딩 부족(이력서 0·provider 미선택·관심회사 0)이면 필요한 CLI 명령 안내 → `stale`이거나 `job_running`이면 "터미널에서 `uvx gethired scrape` 실행" 안내, 사용자가 완료를 알리면 다시 읽음 → `postings`를 등급·회사·이유·링크로 요약
- Codex 등 다른 에이전트는 같은 SKILL.md를 스킬 디렉토리에 복사해 쓴다 (README에 경로만)

## 검증 방법
- 네트워크·LLM 없이 `GETHIRED_DEMO=1 DB_PATH=… RESUME_DIR=…`에서 `resume add → provider claude → interest add toss daangn → scrape --json → postings --json --min-level strong`이 전부 exit 0, strong 2건(toss 1·daangn 1). pytest로 고정
- 미로그인 `scrape --json`은 exit 3 + `login_command`. 한 회사만 실패하면 exit 0 + `failed` 1건
- 한 프로세스가 scrape 중일 때 다른 프로세스의 `scrape`·`provider codex`는 `job_running`, UI 버튼은 토스트
- `uvx --from <휠> gethired scrape --json`이 저장소 밖에서 동작하고, 같은 DB를 `gethired serve`의 UI가 보여준다
- 플러그인: 로컬 경로로 설치한 Claude Code 세션에서 "요즘 나한테 맞는 공고 있어?"에 스킬이 발동해 `status`·`postings`를 읽고 요약한다 (사용자가 수동 확인). `claude plugin validate` 통과
- 기존 pytest·vitest·`just test-e2e` 통과

## 결정 사항 (2026-10-19)
- 락은 DB lease·pid lockfile 대신 `filelock`. 같은 머신의 프로세스 배타엔 OS 파일 락이 정확하고(크래시 시 자동 해제, TTL·heartbeat 없음), Windows는 `filelock`이 분기해 주지만 검증 수단이 없어 미검증으로 둔다. sqlite를 여러 머신이 공유하는 시나리오는 없다
- 스킬 v1은 읽기 전용. `scrape`를 스킬이 돌리지 않는 이유는 Claude Code 안에서 `claude`를 중첩 호출하게 되는 것과 수 분의 실행 시간(Bash 제한). 자동 실행은 autopilot에서
- `scrape --if-stale`·`status --check`·`schema_version`은 소비자가 없어 넣지 않는다. 계약 고정은 uvx 버전 범위로
- 구체 작업 순서·파일 단위 계획·단위 테스트 항목은 `design/plans/plan-0012.md`에 둔다
