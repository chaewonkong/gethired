#!/bin/sh
# playwright webServer. 임시 디렉토리(E2E_TMP)에 DB·이력서·가짜 CLI 로그인 상태를 두고 백엔드를 띄운다.
# E2E_DEMO=1이면 데모 모드(--demo: 가짜 스크래퍼·판정, 고정 시각)로 띄운다.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
tmp=${E2E_TMP:-$(mktemp -d)}
mkdir -p "$tmp/resume"

export DB_PATH="$tmp/app.db"
export RESUME_DIR="$tmp/resume"
export FAKE_AUTH_FILE="$tmp/auth.json"
[ -f "$FAKE_AUTH_FILE" ] || printf '{"claude": true, "codex": false}\n' > "$FAKE_AUTH_FILE"
export PATH="$here/fake-bin:$PATH"

set -- --port "${E2E_PORT:-8765}"
if [ "${E2E_DEMO:-}" = "1" ]; then
  set -- --demo "$@"
fi

cd "$root/backend"
exec env UV_CACHE_DIR=../.uv-cache uv run python -m app "$@"
