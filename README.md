# job-posting

**나에게 맞는 채용 포지션만 모아 보여주는 채용 지원 서비스**

1. 앱을 실행한다
2. 첫 화면에서 이력서를 업로드하고 관심회사를 고른다
3. 스크래핑하기 버튼을 눌러 내 이력서와 매칭되는 채용 포지션만 리스팅해서 확인한다

## 서비스 소개

등록된 회사(네이버, 카카오, 쿠팡, 토스, 당근, 라인, 삼성전자, 현대자동차, 업스테이지, 우아한형제들, 두나무, 42dot, 카카오뱅크, 카카오페이, 하이퍼커넥트)의 채용 사이트를 읽어 내 이력서에 맞는 엔지니어링 포지션을 등급(strong / good / stretch)과 함께 보여주는 로컬 앱.

![데모: 이력서 업로드부터 매칭 결과까지](docs/demo.gif)

- LLM은 Claude Agent SDK + 로컬 Claude Code 로그인 세션(`claude login`)을 사용. API key 불필요. 개인 로컬 용도 전용

## 사용 준비
### 설치와 실행
필요한 것은 [uv](https://docs.astral.sh/uv/) 하나와 AI 하네스 CLI 하나다. Python·Node·just는 필요 없다 (Python 3.14는 uv가 자동으로 내려받는다).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv 설치 (Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex")
uvx job-posting                                   # 서버 실행 + 브라우저 열기 → http://127.0.0.1:8000
```

AI 하네스는 둘 중 하나를 설치하고 로그인해 둔다. 앱 첫 화면에서 고른다.
- Claude Code: `curl -fsSL https://claude.ai/install.sh | bash` 후 `claude login`
- Codex: `brew install codex` (또는 `npm i -g @openai/codex`) 후 `codex login`
- `ANTHROPIC_API_KEY`·`OPENAI_API_KEY`는 설정하지 않음 (있으면 로그인 세션 대신 키가 쓰임)

```bash
uvx job-posting --port 9000 --no-open   # 포트 변경, 브라우저 안 열기
uvx job-posting auth [claude|codex]     # 로그인 상태 확인
uvx job-posting paths                   # 데이터(DB·이력서) 위치
uvx job-posting reset-db                # 공고·판정 이력 삭제
```
데이터는 OS 표준 사용자 디렉토리(macOS `~/Library/Application Support/job-posting/`)에 저장된다. `JOB_POSTING_HOME`으로 바꿀 수 있다.

### 이력서 준비
이력서는 Markdown(`.md`) 또는 PDF(`.pdf`)로 준비해 앱 첫 화면에서 업로드한다. 끌어다 놓거나 클릭해서 올리면 되고, 이후에는 상단 **이력서** 버튼에서 추가·교체·삭제한다.

- 여러 파일을 올릴 수 있다. 이력서 외에 경력기술서, 희망 조건(근무지·비자·도메인·역할) 문서를 함께 올리면 프로필에 반영된다
- 올린 문서를 전부 읽어 프로필(기술·연차·도메인·희망 조건)을 추출하고, 이를 기준으로 공고를 판정한다. 문서가 바뀌면 다음 스크래핑 때 다시 추출한다
- 같은 이름으로 올리면 교체. 파일 크기 제한 없음. 문서당 LLM에 넘기는 텍스트는 50,000자까지
- 텍스트가 없는 PDF(스캔·이미지)는 업로드가 거부된다
- 파일은 로컬 데이터 디렉토리(`uvx job-posting paths`로 확인)의 `resume/`에 저장된다. 외부로는 선택한 AI 하네스에만 전달된다

## 개발 ([just](https://github.com/casey/just) · uv · Node 20+)
```bash
just setup     # 의존성 설치 (uv sync + npm install)
just run       # 프론트 빌드 + 백엔드 실행 → http://localhost:8000
just dev       # 백엔드(reload, 8000) + 프론트 Vite(5173, /api 프록시) 동시 실행
just test      # pytest + vitest
just build-wheel  # 프론트 포함 휠 → backend/dist/
```
개발 중 데이터는 저장소 안 `backend/data/app.db`, `resume/`를 쓴다 (justfile이 `DB_PATH`·`RESUME_DIR`로 지정). 전체 명령은 `just`.

릴리스: `backend/pyproject.toml`의 버전을 올리고 `v<버전>` 태그를 push하면 GitHub Actions가 프론트를 빌드해 휠을 만들고 PyPI와 GitHub Release에 올린다.

## 사용
1. 첫 실행: 이력서 업로드 → 관심회사 선택. 관심회사는 회사 탭의 별로 언제든 바꿀 수 있다
2. 공고 탭에서 **스크래핑 하기** → 관심회사만 병렬 수집 → 신규 공고만 LLM 판정 → 등급이 매겨진 공고 저장
3. 관심회사가 아닌 회사의 공고는 모든 탭에서 보이지 않는다 (DB에는 남아 있어 다시 별을 켜면 돌아온다)
4. 첫 실행은 15개사 기준 약 400건을 판정하므로 수 분 / 구독 사용량 $5 상당. 이후 실행은 신규 공고만
5. 세션이 만료되면 배너가 뜸 → 터미널에서 `claude login` 후 다시 시도


## 동작
```
[브라우저] --/api--> [백엔드 (FastAPI)] ---> sqlite (공고·판정·북마크)
                          |
     [스크래핑 하기] 클릭 |  백그라운드 job, 진행 상황은 화면에 실시간 표시
                          |
                          +-> 1. 프로필   resume/*.md를 읽어 바뀌었으면 Claude가 프로필 추출 (안 바뀌었으면 저장된 프로필 사용)
                          +-> 2. 수집     15개사 채용 사이트를 병렬로 읽음 (한 곳이 실패해도 나머지는 계속)
                          +-> 3. 판정     새로 나온 공고만 Claude가 strong / good / stretch로 판정해 저장
```
- 수집은 사이트별로 짠 일반 코드, LLM은 프로필 추출과 판정에만 쓴다
- LLM은 API key 없이 로컬 `claude login` 세션으로 호출한다
- 한 번 판정한 공고는 다시 판정하지 않아 두 번째 실행부터 빠르고 저렴하다
- 채용 사이트에서 내려간 공고는 목록에서 사라지고, 다시 올라오면 북마크와 함께 돌아온다
- 세션이 만료되면 중단되고, 다음 실행에서 판정 못 한 공고만 이어서 판정한다
