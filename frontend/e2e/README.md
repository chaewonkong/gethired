# e2e (Playwright)

```bash
npm run build && npm run test:e2e     # 루트: just test-e2e
```

- 브라우저는 chromium만. `PLAYWRIGHT_BROWSERS_PATH`는 config가 `frontend/.playwright/`로 잡는다 (gitignore). 최초 1회 `PLAYWRIGHT_BROWSERS_PATH=$PWD/.playwright npx playwright install chromium`
  - 다운로드 호스트: `cdn.playwright.dev` → `storage.googleapis.com`(리다이렉트). sandbox allowedDomains에 둘 다 필요
- 서버: `playwright.config.ts`가 임시 디렉토리를 만들어 `E2E_TMP`에, 포트를 `E2E_PORT`(기본 8765)에 넣고 `e2e/server.sh`를 webServer로 띄운다. 테스트 워커도 같은 env를 상속한다
  - `server.sh`: `DB_PATH=$E2E_TMP/app.db`, `RESUME_DIR=$E2E_TMP/resume`, `FAKE_AUTH_FILE=$E2E_TMP/auth.json`을 export하고 `e2e/fake-bin`을 PATH 앞에 붙여 `uv run python -m app --port $E2E_PORT` 실행. `frontend/dist`를 서빙하므로 build 선행
- 가짜 CLI `fake-bin/claude`, `fake-bin/codex`: `FAKE_AUTH_FILE`(`{"claude": true, "codex": false}`)을 읽는다. 테스트는 `helpers.ts`의 `setAuth({claude?, codex?})`로 바꾼다
- 상태 초기화: 서버는 한 번만 띄우고(`workers: 1`), 각 테스트 앞에서 `resetState()`가 DB 전 테이블의 행과 이력서 파일을 지운다. 백엔드가 `DB_PATH`·`RESUME_DIR` env를 따라야 동작한다
- 데모 녹화: `demo` 프로젝트(`demo.spec.ts`만, 1000×720 · 1x · Asia/Seoul · ko-KR · 비디오 항상 녹화)는 `test:e2e`(`--project chromium`)에서 빠진다. `E2E_DEMO=1 npm run demo:record`로 돌리면 `server.sh`가 `python -m app --demo`(가짜 스크래퍼·판정, 고정 시각)로 띄우고, 골든 패스를 밟은 뒤 비디오를 `DEMO_VIDEO_OUT`(기본 `$E2E_TMP/demo.webm`)에 복사한다. `sh e2e/make-gif.sh <in.webm> <out.gif>`가 ffmpeg 2-pass 팔레트(fps 10, 128색)로 GIF를 만들고 크기·길이를 출력하며 5MB를 넘으면 실패한다. 루트 `just screenshots`가 이 둘을 묶는다. chromium·ffmpeg는 sandbox 밖에서
