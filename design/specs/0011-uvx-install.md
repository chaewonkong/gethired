# spec - uvx 한 줄 설치
## 목표
- 사용자가 just·node 없이 `uv` 하나만 있으면 `uvx gethired`으로 앱을 실행할 수 있다
- 개발자는 기존 `just` 흐름을 그대로 쓴다

## 목표가 아닌 것
- uv·python 없는 단일 바이너리 배포 (PyInstaller 등). 다음 단계로 미룬다
- provider CLI(Claude Code / Codex) 설치 자동화. README에서 네이티브 설치 경로만 안내한다
- 데스크톱 앱, Docker

## 기능
- `backend/`가 설치 가능한 Python 패키지가 된다 (`gethired`, hatchling). 빌드된 프론트엔드(`backend/app/static/`)를 휠에 포함한다
- 콘솔 명령 `gethired`
  - `gethired` / `gethired serve [--port N] [--host H] [--no-open] [--demo]`: 서버를 띄우고 브라우저를 연다
  - `gethired auth [claude|codex]`: provider CLI 로그인 상태 확인
  - `gethired reset-db`: 공고·판정 이력 삭제
  - `gethired paths`: 데이터 디렉토리·DB·이력서 경로 출력
- 데이터는 저장소가 아니라 사용자 디렉토리에 둔다
  - `GETHIRED_HOME` (기본 `platformdirs.user_data_dir("gethired")`) 아래 `app.db`, `resume/`
  - 기존 `DB_PATH`·`RESUME_DIR` env override는 유지하며 `GETHIRED_HOME`보다 우선
  - 개발 시 `justfile`이 `DB_PATH=backend/data/app.db`, `RESUME_DIR=resume`를 내보내 지금과 같은 위치를 쓴다
- 릴리스: `v*` 태그 push → GitHub Actions가 프론트 빌드 → 휠 빌드 → PyPI(trusted publishing) 업로드 + GitHub Release에 휠 첨부
- README 설치 섹션: `uv 설치 → uvx gethired → provider 로그인` 과 개발자용 `just` 섹션을 분리

## 검증 방법
- `cd frontend && npm run build` 후 `backend/app/static/index.html`이 생기고 `frontend/dist/`는 생기지 않는다
- `cd backend && uv build` 로 만든 휠 안에 `app/static/index.html`이 들어 있다
- 저장소 밖 빈 디렉토리에서 `uvx --from <휠 경로> gethired --no-open` 을 실행하면 `http://127.0.0.1:8000`에서 UI와 `/api/companies`가 응답하고, DB·이력서가 `gethired paths`가 출력한 사용자 디렉토리에 생긴다. 저장소의 `backend/data/`, `resume/`는 변하지 않는다
- `just run`, `just dev`, `just test`, `just test-e2e`, `just screenshots`는 변경 전과 같이 동작한다 (경로도 기존 위치)
- `uv run pytest`·`npm test` 통과

## 결정 사항 (2026-10-18)
- 배포 단위는 PyPI 휠. `uvx --from git+...`는 node 없이 프론트를 빌드할 수 없어 1차 경로로 쓰지 않는다. PyPI 이름 `gethired`은 비어 있음(2026-10-18 확인)
- 프론트 빌드 산출물은 커밋하지 않는다 (`backend/app/static/` gitignore). CI가 빌드해 휠에 넣는다
- Vite `build.outDir`를 `../backend/app/static`으로 바꾼다. `frontend/dist/`는 폐기
- 데이터 위치는 platformdirs 표준 경로. 저장소 상대 경로는 개발 환경에서 env로만 재현한다
- 디버그 스크립트(`scripts/`)는 `just` 전용으로 남긴다. 콘솔 명령에는 사용자용 서브커맨드만 둔다
- `uvicorn.run`에 import 문자열 대신 app 객체를 넘긴다 (설치된 패키지에서 cwd 의존 제거, 다음 단계 PyInstaller 대비)
- 실행 계획은 채팅으로 보고. 별도 plan 문서 없음
