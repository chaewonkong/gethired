# job-posting

**나에게 맞는 채용 포지션만 모아 보여주는 채용 지원 서비스**

1. 앱을 실행한다
2. 첫 화면에서 이력서를 업로드하고 관심회사를 고른다
3. 스크래핑하기 버튼을 눌러 내 이력서와 매칭되는 채용 포지션만 리스팅해서 확인한다

## 서비스 소개

등록된 회사(네이버, 카카오, 쿠팡, 토스, 당근, 라인, 삼성전자, 현대자동차, 업스테이지, 우아한형제들, 두나무, 42dot, 카카오뱅크, 카카오페이, 하이퍼커넥트)의 채용 사이트를 읽어 내 이력서에 맞는 엔지니어링 포지션을 등급(strong / good / stretch)과 함께 보여주는 로컬 앱.

- LLM은 Claude Agent SDK + 로컬 Claude Code 로그인 세션(`claude login`)을 사용. API key 불필요. 개인 로컬 용도 전용

## 사용 준비
### 의존성

- Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 20+, Claude Code CLI(`claude login` 완료)
- `ANTHROPIC_API_KEY`는 설정하지 않음 (있으면 세션 대신 키가 쓰임)

### 이력서 준비
이력서는 Markdown(`.md`) 파일로 준비한다. 앱 첫 화면에서 끌어다 놓거나 클릭해 업로드하면 프로젝트 루트의 `resume/`에 저장된다. 이후에는 상단 **이력서** 버튼에서 교체·추가·삭제할 수 있다. `resume/`에 직접 파일을 넣어도 된다.

`resume/` 안의 `*.md`를 전부 읽어 프로필(기술·연차·도메인·희망 조건)을 추출하고, 이를 기준으로 공고를 판정한다.
```
resume/
  resume.md            # 이력서
  career_portfolio.md  # 경력기술서 (선택)
  preferences.md       # 희망 근무지/비자/도메인/역할 (선택)
```
- 파일명·개수는 자유. 같은 이름으로 업로드하면 교체. 파일당 1MB. 하위 디렉토리는 읽지 않음
- `resume/`는 gitignore 대상이라 커밋되지 않음
- 파일 내용이 바뀌면 다음 실행 때 프로필을 다시 추출

## 설치와 실행 ([just](https://github.com/casey/just))
```bash
just setup     # 의존성 설치 (uv sync + npm install)
just run       # 프론트 빌드 + 백엔드 실행 → http://localhost:8000
```
개발 시: `just dev` → 백엔드(reload, 8000) + 프론트 Vite(5173, `/api` 프록시) 동시 실행, http://localhost:5173. 전체 목록은 `just`.

just 없이:
```bash
cd frontend && npm install && npm run build
cd backend && uv sync && uv run python -m app --port 8000
```

## 사용
1. 첫 실행: 이력서 업로드 → 관심회사 선택. 관심회사는 회사 탭의 별로 언제든 바꿀 수 있다
2. 공고 탭에서 **스크래핑 하기** → 관심회사만 병렬 수집 → 신규 공고만 LLM 판정 → 등급이 매겨진 공고 저장
3. 관심회사가 아닌 회사의 공고는 모든 탭에서 보이지 않는다 (DB에는 남아 있어 다시 별을 켜면 돌아온다)
4. 첫 실행은 15개사 기준 약 400건을 판정하므로 수 분 / 구독 사용량 $5 상당. 이후 실행은 신규 공고만
5. 세션이 만료되면 배너가 뜸 → 터미널에서 `claude login` 후 다시 시도

## 테스트
```bash
just test        # 백엔드 + 프론트 단위 테스트 (네트워크/LLM 없음). 따로: just test-api / just test-web
just test-live   # 실제 채용 사이트 호출
```

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
