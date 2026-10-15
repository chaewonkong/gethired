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
|   |   |-- scrapers/         # 회사별 수집기 (+ base.py, greenhouse.py)
|   |   |-- api.py            # REST API
|   |   |-- jobs.py           # 스크래핑 job 실행
|   |   |-- profile.py        # 이력서 -> 프로필
|   |   |-- resume.py         # resume/*.md 파일 목록·저장·삭제
|   |   |-- matcher.py        # LLM 판정
|   |   |-- llm.py            # Claude Agent SDK 래퍼
|   |   |-- repository.py     # sqlite 접근
|   |   `-- main.py           # 앱 조립 + 프론트 정적 서빙
|   |-- scripts/              # 디버그용 단독 실행 (just scrape / just match)
|   |-- tests/                # pytest
|   |-- fixtures/             # 파서 테스트용 응답 샘플
|   `-- data/app.db           # DB (gitignore)
|-- frontend/                 # React + Vite
|   `-- src/
|       |-- App.tsx           # 상태 · 탭 · 폴링
|       |-- api.ts            # 타입 + fetch 래퍼
|       |-- components/       # 탭(Postings, Bookmarks, Hidden, Companies), 온보딩(ResumeDropzone, CompanySelect), ...
|       `-- test/             # vitest 설정 · 픽스처
|-- design/
|   |-- specs/                # 기능 명세 (0001-*.md ...)
|   `-- plans/                # 실행 계획
|-- resume/                   # 이력서 *.md (gitignore)
`-- justfile                  # 실행·테스트 명령
```

## 디버그
- `just scrape [company...]`: 스크래퍼만 실행, `backend/out/<company>.json`
- `just match [company] [--limit N] [--planted]`: 파일 기반 매칭, `backend/out/fit.md`
- `just auth`: 세션 인증 확인 · `just reset-db`: 공고·판정 이력 삭제
