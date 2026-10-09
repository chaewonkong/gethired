"""`uv run python -m app [--port 8000]` — 빌드된 frontend/dist를 정적 서빙하며 API 실행."""
import argparse

import uvicorn

from .config import FRONTEND_DIST


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if not FRONTEND_DIST.exists():
        print(f"warning: {FRONTEND_DIST} not found — run `just build` first (API only)")
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
