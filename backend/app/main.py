import os

from .api import create_app
from .config import DB_PATH, FRONTEND_DIST
from .jobs import JobManager
from .repository import Repository
from .static import SPAStaticFiles

# API key가 있으면 CLI 세션 대신 키가 쓰이므로 앱에서는 항상 제거
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

repo = Repository(DB_PATH)
app = create_app(repo, JobManager(repo))

if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
