from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
RESUME_DIR = ROOT / "resume"
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

MATCH_BATCH_SIZE = 20
MATCH_CONCURRENCY = 4
