# job-posting

등록된 회사(네이버, 카카오, 쿠팡, 토스, 당근, 라인)의 채용 사이트를 읽어 내 이력서에 맞는 엔지니어링 포지션을 등급(strong / good / stretch)과 함께 보여주는 로컬 앱.

- 설계: [design/spec.md](design/spec.md) · PoC 기록: [design/poc.md](design/poc.md)
- LLM은 Claude Agent SDK + 로컬 Claude Code 로그인 세션(`claude login`)을 사용. API key 불필요. 개인 로컬 용도 전용

## 준비
- Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 20+, Claude Code CLI(`claude login` 완료)
- `resume/resume.md`, `resume/career_portfolio.md` (선택: `resume/preferences.md`에 희망 근무지/비자/도메인)
- `ANTHROPIC_API_KEY`는 설정하지 않음 (있으면 세션 대신 키가 쓰임)

## 실행 ([just](https://github.com/casey/just))
```bash
just setup     # 의존성 설치 (uv sync + npm install)
just run       # 프론트 빌드 + 백엔드 실행 → http://localhost:8000
```
개발 시: `just dev-api`(백엔드 reload) + `just dev-web`(Vite 5173, `/api` 프록시). 전체 목록은 `just`.

just 없이:
```bash
cd frontend && npm install && npm run build
cd backend && uv sync && uv run uvicorn app.main:app --port 8000
```

## 사용
1. 공고 탭에서 **스크래핑 하기** → 6개사 병렬 수집 → 신규 공고만 LLM 판정 → 등급이 매겨진 공고 저장
2. 첫 실행은 약 300건을 판정하므로 수 분 / 구독 사용량 $5 상당. 이후 실행은 신규 공고만
3. 세션이 만료되면 배너가 뜸 → 터미널에서 `claude login` 후 다시 시도

## 테스트
```bash
just test        # 단위·API 테스트 (네트워크/LLM 없음)
just test-live   # 실제 채용 사이트 호출
```

## 디버그
- `just scrape [company...]`: 스크래퍼만 실행, `backend/out/<company>.json`
- `just match [company] [--limit N] [--planted]`: 파일 기반 매칭, `backend/out/fit.md`
- `just auth`: 세션 인증 확인 · `just reset-db`: 공고·판정 이력 삭제

## 구조
```
backend/app/   scrapers/ (회사별 구현체·registry) · llm.py · profile.py · matcher.py · repository.py · jobs.py · api.py
frontend/src/  App.tsx · components/ (PostingsTab, PostingCard, ScrapeProgress, CompaniesTab)
design/        spec.md · plan.md · ui-sample.html · poc.md · poc-results/
```
새 회사 추가 = `backend/app/scrapers/<company>.py`에 `Scraper` 구현체 추가 (Greenhouse면 `GreenhouseScraper` 상속).
