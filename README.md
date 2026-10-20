# get-hired

**나에게 맞는 채용 포지션만 모아 보여주는 채용 지원 서비스**

> 설치·실행 명령과 패키지 이름은 `gethired`

1. 앱을 실행한다
2. 첫 화면에서 이력서를 업로드하고 관심회사를 고른다
3. 스크래핑하기 버튼을 눌러 내 이력서와 매칭되는 채용 포지션만 리스팅해서 확인한다

## 서비스 소개

등록된 회사(네이버, 카카오, 쿠팡, 토스, 당근, 라인, 삼성전자, 현대자동차, 업스테이지, 우아한형제들, 두나무, 42dot, 카카오뱅크, 카카오페이, 하이퍼커넥트, 카카오모빌리티, NHN, 컬리, 몰로코, 크래프톤, 오늘의집, 에이블리, 래블업)의 채용 사이트를 읽어 내 이력서에 맞는 엔지니어링 포지션을 등급(strong / good / stretch)과 함께 보여주는 로컬 앱.

지원 직군: 백엔드·프론트엔드·모바일·데이터·ML·인프라·보안·QA·임베디드·게임 클라이언트 등 소프트웨어 엔지니어링 전반. 직군은 이력서에서 읽고, 디자인·PM 등 비개발 직군 공고는 판정에서 제외된다.

카드를 누르면 공고 상세 화면으로 간다. 자격요건·우대사항·기술 스택과 함께 이력서와의 정합성을 축별 막대(핵심 기술 35 · 도메인 35 · 연차 20 · 우대사항 10, 합계 = score)로 보여주고, 공고 원문은 맨 아래에 접어 둔다. **피드백 생성** 버튼을 누르면 그때 LLM이 이 공고 기준으로 이력서에서 보강·강조할 점 3~5개를 만들어 준다. 결과는 이력서별로 저장돼 다시 열면 바로 보이고, 이력서가 바뀌면 이전 피드백은 접히고 버튼이 다시 나타난다.

![데모: 이력서 업로드부터 매칭 결과까지](docs/demo.gif)

- LLM은 Claude Agent SDK + 로컬 Claude Code 로그인 세션(`claude login`)을 사용. API key 불필요. 개인 로컬 용도 전용

## 사용 준비
### 설치와 실행
필요한 것:
-  [uv](https://docs.astral.sh/uv/) 
- Codex/ClaudeCode

```bash
$ uvx gethired                       # 서버 실행 + 브라우저 열기 → http://127.0.0.1:8000
```

<details>
<summary><b>uv가 없다면</b></summary>

```bash
$ curl -LsSf https://astral.sh/uv/install.sh | sh   # uv 설치 (Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex")
```

AI 하네스는 Claude Code와 Codex를 지원.
- `ANTHROPIC_API_KEY`·`OPENAI_API_KEY`는 설정하지 않음 (있으면 로그인 세션 대신 키가 쓰임)

</details>

<details>
<summary><b>고급 사용법</b></summary>

```bash
$ uvx gethired --port 9000 --no-open   # 포트 변경, 브라우저 안 열기
$ uvx gethired auth [claude|codex]     # 로그인 상태 확인
$ uvx gethired paths                   # 데이터(DB·이력서) 위치
$ uvx gethired reset-db                # 공고·판정 이력 삭제
```
데이터는 OS 표준 사용자 디렉토리(macOS `~/Library/Application Support/gethired/`)에 저장된다. `GETHIRED_HOME`으로 바꿀 수 있다.

**CLI**: 브라우저 없이 온보딩 → 스크래핑 → 조회. 서브커맨드마다 `--json`을 붙이면 stdout에 JSON만 나온다 (진행·로그는 stderr)

| 명령 | 동작 |
|---|---|
| `uvx gethired status` | 이력서 수, AI, 관심회사, 회사별 마지막 성공 실행, `stale`(24h 초과), 실행 중 여부 |
| `uvx gethired resume add <file...>` · `resume list` · `resume rm <name>` | 이력서 등록(같은 이름 교체)·목록·삭제 |
| `uvx gethired provider [claude\|codex]` | AI 조회·변경 |
| `uvx gethired companies` | 등록 회사 + 관심 여부 + 마지막 실행 |
| `uvx gethired interest add\|rm <company...>` | 관심회사 설정 |
| `uvx gethired scrape [company...]` | 스크래핑·판정을 끝까지 실행. 진행은 회사별로 stderr |
| `uvx gethired postings [--min-level good] [--company ...] [--since 24h] [--limit N] [--full]` | 저장된 공고 (숨김 제외·관심회사만·score순) |
| `uvx gethired posting <id> [--body]` | 공고 상세 1건: 요건·우대사항·축별 점수·캐시된 피드백. `--body`면 공고 원문 포함 (피드백 생성은 UI에서만) |

- exit code: 0 성공(일부 회사 실패는 `failed`) · 1 실패·입력 오류·다른 곳에서 실행 중(`job_running`) · 3 로그인 필요(`login_command`) · 130 Ctrl+C
- UI와 CLI는 같은 DB를 쓴다. 스크래핑은 한 번에 하나만 (파일 락. Windows는 **미검증**)

</details>

### 이력서 준비
이력서는 Markdown(`.md`) 또는 PDF(`.pdf`)로 준비해 앱 첫 화면에서 업로드한다. 끌어다 놓거나 클릭해서 올리면 되고, 이후에는 상단 **이력서** 버튼에서 추가·교체·삭제한다.

- 여러 파일을 올릴 수 있다. 이력서 외에 경력기술서, 희망 조건(근무지·비자·도메인·역할) 문서를 함께 올리면 프로필에 반영된다
- 올린 문서를 전부 읽어 프로필(기술·연차·도메인·희망 조건)을 추출하고, 이를 기준으로 공고를 판정한다. 문서가 바뀌면 다음 스크래핑 때 다시 추출한다
- 같은 이름으로 올리면 교체. 파일 크기 제한 없음. 문서당 LLM에 넘기는 텍스트는 50,000자까지
- 텍스트가 없는 PDF(스캔·이미지)는 업로드가 거부된다
- 파일은 로컬 데이터 디렉토리(`uvx gethired paths`로 확인)의 `resume/`에 저장된다. 외부로는 선택한 AI 하네스에만 전달된다

<details>
<summary><b>개발</b> [just](https://github.com/casey/just) · uv · Node 20+</summary>

```bash
$ just setup     # 의존성 설치 (uv sync + npm install)
$ just run       # 프론트 빌드 + 백엔드 실행 → http://localhost:8000
$ just dev       # 백엔드(reload, 8000) + 프론트 Vite(5173, /api 프록시) 동시 실행
$ just lint      # ruff + tsc + eslint
$ just test      # pytest + vitest
$ just build-wheel  # 프론트 포함 휠 → backend/dist/
```
개발 중 데이터는 저장소 안 `backend/data/app.db`, `resume/`를 쓴다 (justfile이 `DB_PATH`·`RESUME_DIR`로 지정). 전체 명령은 `just`.

릴리스: `backend/pyproject.toml`의 버전을 올리고 `v<버전>` 태그를 push하면 GitHub Actions가 프론트를 빌드해 휠을 만들고 PyPI와 GitHub Release에 올린다.

</details>

## 사용
1. 첫 실행: 이력서 업로드 → 관심회사 선택. 관심회사는 회사 탭의 별로 언제든 바꿀 수 있다
2. 공고 탭에서 **스크래핑 하기** → 관심회사만 병렬 수집 → 신규 공고만 LLM 판정 → 등급이 매겨진 공고 저장
3. 관심회사가 아닌 회사의 공고는 모든 탭에서 보이지 않는다 (DB에는 남아 있어 다시 별을 켜면 돌아온다)
4. 첫 실행은 23개사 기준 약 600건을 판정하므로 수 분 / 구독 사용량 $7 상당. 이후 실행은 신규 공고만
5. 세션이 만료되면 배너가 뜸 → 터미널에서 `claude login` 후 다시 시도

## 에이전트에서 쓰기
Claude Code 플러그인으로 설치하면 "요즘 나한테 맞는 공고 있어?" 같은 질문에 에이전트가 CLI로 상태·공고를 읽어 요약한다.

```bash
$ claude plugin marketplace add chaewonkong/gethired
$ claude plugin install gethired@gethired
```
- 호출: `/gethired:jobs`, 또는 구직·공고·이직 관련 질문이면 자동 발동
- 읽기 전용이다 (`status`·`postings`·`companies`·`posting`). 스크래핑이 필요하면 터미널에서 `uvx gethired scrape`를 직접 실행하라고 안내한다
- sandbox에서는 uv 캐시·PyPI 접근이 막혀 sandbox 밖 실행 승인을 매번 묻는다. `~/.claude/settings.json`의 `permissions.allow`에 `Bash(uvx --from gethired~=0.4.0 gethired *)`를 추가하면 이 명령만 승인 없이 sandbox 밖에서 실행된다
  - sandbox 안에서 돌리려면 대신 `sandbox.filesystem.allowWrite`에 `~/.cache/uv`·`~/.local/share/uv`, `sandbox.network.allowedDomains`에 `pypi.org`·`files.pythonhosted.org`를 넣는다. 단 sandbox 안의 모든 명령이 uv 캐시를 쓸 수 있게 되므로 권장하지 않는다
- Codex 등 다른 에이전트: [`plugin/skills/jobs/SKILL.md`](plugin/skills/jobs/SKILL.md)를 그 에이전트의 스킬 디렉토리(Codex: `~/.agents/skills/gethired-jobs/SKILL.md`)에 복사한다


<details>
<summary><b>동작</b></summary>

```
[브라우저] --/api--> [백엔드 (FastAPI)] ---> sqlite (공고·판정·북마크)
                          |
     [스크래핑 하기] 클릭 |  백그라운드 job, 진행 상황은 화면에 실시간 표시
                          |
                          +-> 1. 프로필   resume/*.md를 읽어 바뀌었으면 Claude가 프로필 추출 (안 바뀌었으면 저장된 프로필 사용)
                          +-> 2. 수집     23개사 채용 사이트를 병렬로 읽음 (한 곳이 실패해도 나머지는 계속)
                          +-> 3. 판정     새로 나온 공고만 Claude가 strong / good / stretch로 판정해 저장
```
- 수집은 사이트별로 짠 일반 코드, LLM은 프로필 추출과 판정에만 쓴다
- LLM은 API key 없이 로컬 `claude login` 세션으로 호출한다
- 한 번 판정한 공고는 다시 판정하지 않아 두 번째 실행부터 빠르고 저렴하다 (축별 점수가 없는 이전 버전 판정만 1회 재판정)
- 채용 사이트에서 내려간 공고는 목록에서 사라지고, 다시 올라오면 북마크와 함께 돌아온다
- 세션이 만료되면 중단되고, 다음 실행에서 판정 못 한 공고만 이어서 판정한다

</details>
