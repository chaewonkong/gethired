import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
RESUME_DIR = Path(os.environ.get("RESUME_DIR") or ROOT / "resume")
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = Path(os.environ.get("DB_PATH") or DATA_DIR / "app.db")
FRONTEND_DIST = ROOT / "frontend" / "dist"

MATCH_BATCH_SIZE = 20
MATCH_CONCURRENCY = 4

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude")
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "600"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_MODEL = os.environ.get("CODEX_MODEL") or None
