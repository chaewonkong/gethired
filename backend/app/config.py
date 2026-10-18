import os
from pathlib import Path

from platformdirs import user_data_dir

APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = APP_DIR / "static"

# 사용자 데이터. 개발 시에는 justfile이 DB_PATH·RESUME_DIR로 저장소 안 경로를 넘긴다
HOME = Path(os.environ.get("GETHIRED_HOME") or user_data_dir("gethired"))
DB_PATH = Path(os.environ.get("DB_PATH") or HOME / "app.db")
RESUME_DIR = Path(os.environ.get("RESUME_DIR") or HOME / "resume")

MATCH_BATCH_SIZE = 20
MATCH_CONCURRENCY = 4

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude")
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "600"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_MODEL = os.environ.get("CODEX_MODEL") or None
