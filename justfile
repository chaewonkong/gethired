set shell := ["zsh", "-cu"]

port := "8000"

# 개발 중에는 데이터를 저장소 안에 둔다 (설치형은 platformdirs 사용자 디렉토리)
export DB_PATH := justfile_directory() + "/backend/data/app.db"
export RESUME_DIR := justfile_directory() + "/resume"

default:
    @just --list

# 의존성 설치 (backend + frontend)
setup:
    cd backend && uv sync
    cd frontend && npm install

# 프론트엔드 빌드 → backend/app/static/
build:
    cd frontend && npm run build

# 프론트엔드 빌드 후 정적 서빙 + API 실행 → http://localhost:8000
run: build
    cd backend && uv run gethired --port {{port}}

# 개발 모드: 백엔드(reload, 8000) + 프론트 Vite(5173, /api 프록시) 동시 실행. Ctrl-C로 둘 다 종료
dev:
    #!/usr/bin/env zsh
    set -u
    # kill 0은 셸 자신에게도 TERM을 보내므로, 종료 처리 중에는 셸이 INT/TERM을 무시해야 trap이 재귀하지 않는다
    trap 'trap "" INT TERM; kill 0; wait' EXIT
    trap 'exit 130' INT TERM
    (cd backend && uv run uvicorn app.main:app --port {{port}} --reload) &
    (cd frontend && npm run dev) &
    wait

# 백엔드만 실행
dev-api:
    cd backend && uv run uvicorn app.main:app --port {{port}} --reload

# 프론트엔드 개발 서버 (5173, /api는 8000으로 프록시)
dev-web:
    cd frontend && npm run dev

# 단위·API 테스트 (네트워크/LLM 없음): 백엔드 + 프론트엔드
test: test-api test-web

# 백엔드 단위·API 테스트
test-api:
    cd backend && uv run pytest

# 프론트엔드 단위 테스트 (vitest, jsdom)
test-web:
    cd frontend && npm test

# 실제 채용 사이트 호출 통합 테스트
test-live:
    cd backend && LIVE=1 uv run pytest tests/test_scrapers_live.py

# 브라우저 e2e (Playwright, chromium). sandbox 안에서는 chromium이 못 떠서 밖에서 실행
test-e2e: build
    cd frontend && npm run test:e2e

# e2e 최초 1회: chromium 설치 (frontend/.playwright/)
e2e-install:
    cd frontend && PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright npx playwright install chromium

# README 데모 GIF 녹화 → docs/demo.gif (데모 모드 백엔드, chromium·ffmpeg 필요, sandbox 밖에서)
screenshots: build
    #!/usr/bin/env zsh
    set -eu
    tmp=$(mktemp -d)
    cd frontend
    E2E_DEMO=1 E2E_TMP="$tmp" npm run demo:record
    sh e2e/make-gif.sh "$tmp/demo.webm" ../docs/demo.gif

# 휠 빌드 (프론트 포함) → backend/dist/
build-wheel: build
    cd backend && uv build

# 스크래퍼만 실행 → backend/out/<company>.json
scrape *companies:
    cd backend && uv run python scripts/run_scrape.py {{companies}}

# 파일 기반 매칭 → backend/out/fit.md (예: just match daangn --limit 10 --provider codex)
match *args:
    cd backend && uv run python scripts/match.py {{args}}

# 이력서 텍스트 추출 확인 → backend/out/resume_text/<name>.txt (예: just resume-text resume.pdf)
resume-text *args:
    cd backend && uv run python scripts/resume_text.py {{args}}

# provider CLI 로그인 확인 (예: just auth codex)
auth provider="claude":
    cd backend && uv run gethired auth {{provider}}

# DB 초기화 (공고·판정 이력 삭제)
reset-db:
    cd backend && uv run gethired reset-db
