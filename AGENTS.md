## Permission Policy (override)
- .claude/settings.json의 allow 목록에 있는 작업은 사전 허락된 것으로 간주하고 묻지 않고 실행한다.
- 그 외 작업은 글로벌 정책대로 허락을 받는다.

## 문서 지도
- 설계: [design/specs/](design/specs/) · 계획: [design/plans/](design/plans/)
- 모듈별 상세: [backend/AGENTS.md](backend/AGENTS.md), [frontend/AGENTS.md](frontend/AGENTS.md)

## 구조
```
job-posting/
|-- backend/                  # FastAPI + sqlite
|   |-- app/
|   |   |-- __main__.py       # 콘솔 진입점 gethired → cli.main
|   |   |-- cli.py            # 서브커맨드 (serve·auth·reset-db·paths·status·resume·provider·companies·interest·scrape·postings), --json
|   |   |-- static/           # 프론트 빌드 산출물 (gitignore, 휠에 포함)
|   |   |-- scrapers/         # 회사별 수집기 (+ base.py, greenhouse.py)
|   |   |-- api.py            # REST API
|   |   |-- jobs.py           # 스크래핑 job 실행 + 프로세스 간 락(filelock)
|   |   |-- profile.py        # 이력서 -> 프로필
|   |   |-- resume.py         # resume/ 파일 목록·저장·삭제, md·pdf 텍스트 추출
|   |   |-- matcher.py        # LLM 판정
|   |   |-- llm.py            # LLM 호출 (Claude Agent SDK / Codex CLI)
|   |   |-- auth.py           # provider CLI 로그인 확인
|   |   |-- repository.py     # sqlite 접근
|   |   |-- demo.py           # 데모 모드 (가짜 스크래퍼·판정, 고정 시각) — README GIF 녹화용
|   |   `-- main.py           # 앱 조립 + 프론트 정적 서빙
|   |-- scripts/              # 디버그용 단독 실행 (just scrape / just match)
|   |-- tests/                # pytest
|   |-- fixtures/             # 파서 테스트용 응답 샘플
|   `-- data/app.db           # 개발용 DB (gitignore). 설치형은 platformdirs 사용자 디렉토리
|-- frontend/                 # React + Vite
|   `-- src/
|       |-- App.tsx           # 상태 · 탭 · 폴링
|       |-- api.ts            # 타입 + fetch 래퍼
|       |-- components/       # 탭(Postings, Bookmarks, Hidden, Companies), 온보딩(ResumeDropzone, ProviderSelect, CompanySelect), ...
|       |-- test/             # vitest 설정 · 픽스처
|       `-- e2e/              # Playwright (just test-e2e, sandbox 밖에서) + 데모 녹화(demo.spec.ts, make-gif.sh)
|-- .claude-plugin/          # marketplace.json (Claude Code 마켓플레이스, plugins[0] → ./plugin)
|-- plugin/                   # Claude Code 플러그인 gethired: .claude-plugin/plugin.json, skills/jobs/SKILL.md (읽기 전용 CLI 호출)
|-- .github/workflows/        # ci-backend.yml(ruff·pytest) · ci-frontend.yml(tsc·eslint·vitest) · release.yml(v* 태그 → 휠 → PyPI + Release)
|-- design/
|   |-- specs/                # 기능 명세 (0001-*.md ...)
|   `-- plans/                # 실행 계획
|-- docs/demo.gif             # README 데모 GIF (just screenshots로 갱신)
|-- resume/                   # 개발용 이력서 *.md, *.pdf (gitignore). 설치형은 사용자 디렉토리
`-- justfile                  # 실행·테스트 명령
```

## 디버그
- `just scrape [company...]`: 스크래퍼만 실행, `backend/out/<company>.json`
- `just match [company] [--limit N] [--planted] [--provider codex]`: 파일 기반 매칭, `backend/out/fit.md`
- `just resume-text [file...]`: 이력서 텍스트 추출 결과, `backend/out/resume_text/`
- `just lint`: ruff + tsc + eslint (CI와 동일. `lint-api`·`lint-web`로 분리 실행)
- `just plugin-validate`: 마켓플레이스·플러그인 매니페스트 검증. SKILL.md의 JSON 키·code는 `backend/tests/test_cli.py`의 키 집합 테스트와 맞춘다
- `just auth [claude|codex]`: provider CLI 로그인 확인 · `just reset-db`: 공고·판정 이력 삭제 · `just build-wheel`: 휠 빌드(`backend/dist/`)
- `just screenshots`: 데모 모드로 골든 패스를 녹화해 `docs/demo.gif` 갱신 (chromium·ffmpeg, sandbox 밖에서 사용자가)
