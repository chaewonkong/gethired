"""`gethired <command> [--json]` — 서버(serve)와 헤드리스 명령. 서브커맨드 생략 = serve.
--json이면 stdout에는 JSON만, 로그·진행은 stderr. 오류는 {code, message, login_command?} + exit code."""
import argparse
import asyncio
import json
import os
import sys
import threading
import webbrowser
from collections.abc import AsyncIterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn

from . import auth, config, resume
from .llm import PROVIDERS, resolve_provider
from .repository import Repository, now_iso

COMMANDS = ("serve", "auth", "reset-db", "paths", "resume", "provider", "companies", "interest")
LOGIN_COMMAND = {"claude": "claude login", "codex": f"{config.CODEX_BIN} login"}
CHUNK = 1 << 20


class Fail(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 1, login_command: str | None = None):
        super().__init__(message)
        self.body = {"code": code, "message": message}
        if login_command:
            self.body["login_command"] = login_command
        self.exit_code = exit_code


def _fail(code: str, message: str, exit_code: int = 1, login_command: str | None = None):
    raise Fail(code, message, exit_code, login_command)


def _table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    cells = [[("" if r.get(c) is None else str(r.get(c))) for c in cols] for r in rows]
    widths = [max([len(c), *(len(row[i]) for row in cells)]) for i, c in enumerate(cols)]
    return "\n".join("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip() for row in [cols, *cells])


def _emit(obj: Any, as_json: bool, human: str | None = None) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False))
    elif human is not None:
        print(human)
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        print(_table(obj, list(obj[0])))
    elif isinstance(obj, dict):
        print("\n".join(f"{k}: {v}" for k, v in obj.items()))
    else:
        print(obj)


@dataclass
class Env:
    db_path: Path
    resume_dir: Path
    demo: bool

    def repo(self) -> Repository:
        return Repository(self.db_path)

    def scrapers(self) -> dict:
        if self.demo:
            from .demo import SCRAPERS
            return dict(SCRAPERS)
        from .scrapers import REGISTRY
        return REGISTRY


def _env() -> Env:
    if os.environ.get("GETHIRED_DEMO") == "1":
        from .demo import demo_paths, set_fixed_now, FIXED_NOW
        db_path, resume_dir = demo_paths()
        if not db_path or not resume_dir:
            _fail("invalid_argument", "데모 모드(GETHIRED_DEMO=1)에서는 DB_PATH·RESUME_DIR을 지정해야 합니다.")
        set_fixed_now(FIXED_NOW)
        return Env(db_path, resume_dir, demo=True)
    return Env(config.DB_PATH, config.RESUME_DIR, demo=False)


# --- 기존 명령 ---
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


def _auth(args: argparse.Namespace) -> int:
    ok = asyncio.run(auth.is_logged_in(args.provider))
    cmd = LOGIN_COMMAND[args.provider]
    _emit({"provider": args.provider, "logged_in": ok, "login_command": cmd}, args.json,
          f"{args.provider}: {'logged in' if ok else 'not logged in — run `' + cmd + '`'}")
    return 0 if ok else 1


def _reset_db(args: argparse.Namespace) -> None:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
        print(f"removed {config.DB_PATH}")
    else:
        print(f"no db at {config.DB_PATH}")


def _paths(args: argparse.Namespace) -> None:
    paths = {"home": str(config.HOME), "db": str(config.DB_PATH), "resume": str(config.RESUME_DIR),
             "frontend": str(config.FRONTEND_DIST)}
    _emit(paths, args.json, "\n".join(f"{k + ':':<10}{v}" for k, v in paths.items()))


# --- 온보딩 ---
async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            yield chunk


def _resume_files(env: Env, as_json: bool) -> None:
    files = resume.list_files(env.resume_dir)
    _emit(files, as_json, _table(files, ["name", "size", "updated_at"]) if files else "(no resume)")


def _resume(args: argparse.Namespace) -> None:
    env = _env()
    if args.action == "add":
        for f in map(Path, args.files):
            if not f.is_file():
                _fail("invalid_argument", f"file not found: {f}")
            try:
                asyncio.run(resume.save(env.resume_dir, f.name, _file_chunks(f)))
            except ValueError as e:
                _fail("invalid_resume", str(e))
    elif args.action == "rm":
        try:
            found = resume.delete(env.resume_dir, args.name)
        except ValueError as e:
            _fail("invalid_argument", str(e))
        if not found:
            _fail("invalid_argument", f"resume file not found: {args.name}")
    _resume_files(env, args.json)


def _provider(args: argparse.Namespace) -> None:
    env = _env()
    with closing(env.repo()) as repo:
        if args.name:
            repo.set_setting("provider", args.name, now_iso())
        stored = repo.get_setting("provider")
    _emit({"provider": resolve_provider(stored), "chosen": stored is not None}, args.json)


def _companies(args: argparse.Namespace) -> None:
    env = _env()
    with closing(env.repo()) as repo:
        last = repo.last_runs()
        interests = set(repo.list_interests())
    rows = [{"company": name, "display_name": cls.display_name, "careers_url": cls.careers_url,
             "last_run": last.get(name), "interested": name in interests}
            for name, cls in env.scrapers().items()]
    human = _table([{"company": r["company"], "name": r["display_name"], "interested": "*" if r["interested"] else "",
                     "last_run": r["last_run"] and f"{r['last_run']['status']} {r['last_run']['finished_at'] or ''}"}
                    for r in rows], ["company", "name", "interested", "last_run"])
    _emit(rows, args.json, human)


def _interest(args: argparse.Namespace) -> None:
    env = _env()
    unknown = [c for c in args.companies if c not in env.scrapers()]
    if unknown:
        _fail("invalid_argument", f"unknown companies: {unknown}")
    with closing(env.repo()) as repo:
        for c in args.companies:
            repo.set_interest(c, args.action == "add", now_iso())
        interests = repo.list_interests()
    _emit({"companies": interests}, args.json, " ".join(interests) or "(no interests)")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        _fail("invalid_argument", f"{self.prog}: {message}")


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="gethired")
    sub = ap.add_subparsers(dest="command", required=True, parser_class=_Parser)

    js = argparse.ArgumentParser(add_help=False)
    js.add_argument("--json", action="store_true", help="stdout에 JSON만 출력")

    def cmd(name: str, func, help: str, as_json: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help, parents=[js] if as_json else [])
        p.set_defaults(func=func)
        return p

    serve = cmd("serve", _serve, "서버 실행 후 브라우저 열기 (기본)", as_json=False)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    serve.add_argument("--demo", action="store_true", help="고정 데이터 데모 모드 (네트워크·LLM·실제 경로 없음)")

    cmd("auth", _auth, "provider CLI 로그인 상태 확인").add_argument(
        "provider", nargs="?", default="claude", choices=PROVIDERS)
    cmd("reset-db", _reset_db, "공고·판정 이력 삭제", as_json=False)
    cmd("paths", _paths, "데이터 경로 출력")

    rs = cmd("resume", _resume, "이력서 등록·목록·삭제", as_json=False)
    rsub = rs.add_subparsers(dest="action", required=True, parser_class=_Parser)
    rsub.add_parser("add", help="이력서 파일 복사 등록 (.md·.pdf, 같은 이름 덮어쓰기)", parents=[js]).add_argument(
        "files", nargs="+")
    rsub.add_parser("list", help="등록된 이력서", parents=[js])
    rsub.add_parser("rm", help="이력서 삭제", parents=[js]).add_argument("name")

    cmd("provider", _provider, "AI provider 조회·설정").add_argument("name", nargs="?", choices=PROVIDERS)
    cmd("companies", _companies, "등록 회사·관심 여부·마지막 실행")

    it = cmd("interest", _interest, "관심회사 추가·해제")
    it.add_argument("action", choices=("add", "rm"))
    it.add_argument("companies", nargs="+")
    return ap


def main(argv: list[str] | None = None) -> int:
    # API key가 있으면 CLI 세션 대신 키가 쓰이므로 항상 제거
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS and argv[0] not in ("-h", "--help"):
        argv.insert(0, "serve")
    as_json = "--json" in argv
    try:
        args = build_parser().parse_args(argv)
        return args.func(args) or 0
    except Fail as e:
        if as_json:
            print(json.dumps(e.body, ensure_ascii=False))
        else:
            print(f"error: {e.body['message']}", file=sys.stderr)
            if "login_command" in e.body:
                print(f"run: {e.body['login_command']}", file=sys.stderr)
        return e.exit_code
