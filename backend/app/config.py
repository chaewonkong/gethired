from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
RESUME_DIR = ROOT / "resume"
RESUME_FILES = [RESUME_DIR / "resume.md", RESUME_DIR / "career_portfolio.md"]
PREFERENCES_FILE = RESUME_DIR / "preferences.md"  # 선택: 희망 근무지/비자/도메인 등
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

MATCH_BATCH_SIZE = 20
MATCH_CONCURRENCY = 4
