"""`gethired [serve|auth|reset-db|paths]` — 빌드된 프론트(app/static)를 정적 서빙하며 API 실행.
`python -m app [--port N] [--demo]`도 같다 (서브커맨드 생략 = serve)."""
import argparse
import asyncio
import sys
import threading
import webbrowser

import uvicorn

from . import auth, config

COMMANDS = ("serve", "auth", "reset-db", "paths")
LOGIN_COMMAND = {"claude": "claude login", "codex": f"{config.CODEX_BIN} login"}


def _load_app():
    from .main import app
    return app


def _serve(args: argparse.Namespace) -> None:
    if not config.FRONTEND_DIST.exists():
        print(f"warning: {config.FRONTEND_DIST} not found — frontend not built (API only)", file=sys.stderr)
    if args.demo:
        from .demo import make_app
        app = make_app()
    else:
        app = _load_app()
    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    print(f"gethired: {url}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port)


def _auth(args: argparse.Namespace) -> None:
    ok = asyncio.run(auth.is_logged_in(args.provider))
    print(f"{args.provider}: {'logged in' if ok else 'not logged in — run `' + LOGIN_COMMAND[args.provider] + '`'}")
    sys.exit(0 if ok else 1)


def _reset_db(args: argparse.Namespace) -> None:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
        print(f"removed {config.DB_PATH}")
    else:
        print(f"no db at {config.DB_PATH}")


def _paths(args: argparse.Namespace) -> None:
    print(f"home:     {config.HOME}")
    print(f"db:       {config.DB_PATH}")
    print(f"resume:   {config.RESUME_DIR}")
    print(f"frontend: {config.FRONTEND_DIST}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gethired")
    sub = ap.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="서버 실행 후 브라우저 열기 (기본)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    serve.add_argument("--demo", action="store_true", help="고정 데이터 데모 모드 (네트워크·LLM·실제 경로 없음)")
    serve.set_defaults(func=_serve)

    au = sub.add_parser("auth", help="provider CLI 로그인 상태 확인")
    au.add_argument("provider", nargs="?", default="claude", choices=("claude", "codex"))
    au.set_defaults(func=_auth)

    sub.add_parser("reset-db", help="공고·판정 이력 삭제").set_defaults(func=_reset_db)
    sub.add_parser("paths", help="데이터 경로 출력").set_defaults(func=_paths)
    return ap


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS and argv[0] not in ("-h", "--help"):
        argv.insert(0, "serve")
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
