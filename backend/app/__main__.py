"""`uv run python -m app [--port 8000] [--demo]` — 빌드된 frontend/dist를 정적 서빙하며 API 실행."""
import argparse
import os
import sys

import uvicorn

from .config import FRONTEND_DIST


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--demo", action="store_true", help="고정 데이터 데모 모드 (네트워크·LLM·실제 경로 없음)")
    args = ap.parse_args()
    if not FRONTEND_DIST.exists():
        print(f"warning: {FRONTEND_DIST} not found — run `just build` first (API only)", file=sys.stderr)
    if args.demo:
        os.environ["JOB_POSTING_DEMO"] = "1"
        uvicorn.run("app.demo:app", host=args.host, port=args.port)
        return
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
