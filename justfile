set shell := ["zsh", "-cu"]

port := "8000"

default:
    @just --list

# 의존성 설치 (backend + frontend)
setup:
    cd backend && uv sync
    cd frontend && npm install

# 프론트엔드 빌드
build:
    cd frontend && npm run build

# 앱 실행 (빌드된 프론트엔드를 함께 서빙) → http://localhost:8000
run: build
    cd backend && uv run uvicorn app.main:app --port {{port}}

# 개발 모드: 백엔드(reload, 8000) + 프론트 Vite(5173, /api 프록시) 동시 실행. Ctrl-C로 둘 다 종료
dev:
    #!/usr/bin/env zsh
    set -u
    trap 'kill 0' EXIT INT TERM
    (cd backend && uv run uvicorn app.main:app --port {{port}} --reload) &
    (cd frontend && npm run dev) &
    wait

# 백엔드만 실행
dev-api:
    cd backend && uv run uvicorn app.main:app --port {{port}} --reload

# 프론트엔드 개발 서버 (5173, /api는 8000으로 프록시)
dev-web:
    cd frontend && npm run dev

# 단위·API 테스트 (네트워크/LLM 없음)
test:
    cd backend && uv run pytest

# 실제 채용 사이트 호출 통합 테스트
test-live:
    cd backend && LIVE=1 uv run pytest tests/test_scrapers_live.py

# 스크래퍼만 실행 → backend/out/<company>.json
scrape *companies:
    cd backend && uv run python scripts/run_scrape.py {{companies}}

# 파일 기반 매칭 → backend/out/fit.md (예: just match daangn --limit 10)
match *args:
    cd backend && uv run python scripts/match.py {{args}}

# Claude 세션 인증 확인
auth:
    claude auth status

# DB 초기화 (공고·판정 이력 삭제)
reset-db:
    rm -f backend/data/app.db
