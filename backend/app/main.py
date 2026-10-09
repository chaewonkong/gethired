import os

from fastapi.staticfiles import StaticFiles

from .api import create_app
from .config import DB_PATH, FRONTEND_DIST
from .jobs import JobManager
from .repository import Repository

# ANTHROPIC_API_KEY가 있으면 세션 대신 키가 쓰이므로 앱에서는 항상 제거
os.environ.pop("ANTHROPIC_API_KEY", None)

repo = Repository(DB_PATH)
app = create_app(repo, JobManager(repo))

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
