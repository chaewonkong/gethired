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
