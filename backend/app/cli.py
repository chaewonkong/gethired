"""`gethired <command> [--json]` — 서버(serve)와 헤드리스 명령. 서브커맨드 생략 = serve.
--json이면 stdout에는 JSON만, 로그·진행은 stderr. 오류는 {code, message, login_command?, job?} + exit code."""
import argparse
import asyncio
import json
import os
import re
import sys
import threading
import webbrowser
from collections.abc import AsyncIterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import uvicorn

from . import auth, config, resume
from .jobs import Job, JobManager, JobRunning, LoginRequired, NoTargets
from .llm import PROVIDERS, resolve_provider
from .repository import LEVEL_RANK, Repository, now_iso

COMMANDS = ("serve", "auth", "reset-db", "paths", "resume", "provider", "companies", "interest",
            "status", "scrape", "postings")
LOGIN_COMMAND = {"claude": "claude login", "codex": f"{config.CODEX_BIN} login"}
CHUNK = 1 << 20
PROGRESS_S = 1.0
POSTING_FIELDS = ("id", "company", "title", "fit_level", "score", "fit_reason", "apply_url", "deadline", "scraped_at")
FULL_FIELDS = (*POSTING_FIELDS, "summary", "gaps")  # 본문은 저장하지 않는다. summary는 LLM 요약


class Fail(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 1, login_command: str | None = None,
                 job: dict | None = None):
        super().__init__(message)
        self.body: dict[str, Any] = {"code": code, "message": message}
        if login_command:
            self.body["login_command"] = login_command
        if job is not None:
            self.body["job"] = job
        self.exit_code = exit_code


def _fail(code: str, message: str, exit_code: int = 1, login_command: str | None = None, job: dict | None = None):
    raise Fail(code, message, exit_code, login_command, job)


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

    def read_repo(self, required: bool = True) -> Repository | None:
        """mode=ro. DB가 없으면 not_onboarded (required=False면 None)"""
        try:
            return Repository(self.db_path, readonly=True)
        except FileNotFoundError:
            if required:
                _fail("not_onboarded", f"DB가 없습니다({self.db_path}). resume add·provider·interest add로 온보딩하세요.")
            return None

    def jobs(self, repo: Repository) -> JobManager:
        lock_path = self.db_path.with_suffix(".lock")
        if self.demo:
            from .demo import make_jobs
            return make_jobs(repo, lock_path)
        return JobManager(repo, lock_path=lock_path)

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
    if args.name:
        with closing(env.repo()) as repo:
            if env.jobs(repo).is_locked():
                _fail("job_running", "스크래핑 중에는 AI를 바꿀 수 없습니다.")
            repo.set_setting("provider", args.name, now_iso())
            stored = repo.get_setting("provider")
    else:
        stored = None
        if repo := env.read_repo(required=False):
            with closing(repo):
                stored = repo.get_setting("provider")
    _emit({"provider": resolve_provider(stored), "chosen": stored is not None}, args.json)


def _companies(args: argparse.Namespace) -> None:
    env = _env()
    last, interests = {}, set()
    if repo := env.read_repo(required=False):  # 온보딩 전에도 목록은 보여준다
        with closing(repo):
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


# --- 조회·스크래핑 ---
def _status(args: argparse.Namespace) -> None:
    env = _env()
    with closing(env.read_repo()) as repo:
        stored = repo.get_setting("provider")
        interests = repo.list_interests()
        body = {"resume_count": len(resume.list_files(env.resume_dir)), "provider": resolve_provider(stored),
                "chosen": stored is not None, "interests": interests, "last_success": repo.last_success_runs(),
                # 관심회사가 없으면 읽을 데이터도 없다
                "stale": not interests or repo.stale(interests, now_iso()),
                "job_running": env.jobs(repo).is_locked()}
    last = ", ".join(f"{c} {r['finished_at']}" for c, r in body["last_success"].items()) or "-"
    _emit(body, args.json, "\n".join(f"{k}: {last if k == 'last_success' else v}" for k, v in body.items()))


def _since_arg(value: str) -> str:
    if not re.fullmatch(r"\d+[hd]", value):
        raise argparse.ArgumentTypeError(f"invalid value {value!r} (예: 24h, 7d)")
    return value


def _since(value: str) -> str:
    n, unit = int(value[:-1]), value[-1]
    delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
    return (datetime.fromisoformat(now_iso()) - delta).isoformat(timespec="seconds")


def _postings(args: argparse.Namespace) -> None:
    env = _env()
    since = args.since and _since(args.since)  # _env()가 데모 고정 시각을 건 뒤에 계산
    with closing(env.read_repo()) as repo:
        rows = repo.list_postings(min_level=args.min_level, include_hidden=False, interests_only=True, since=since)
    if args.company:
        rows = [r for r in rows if r["company"] in args.company]
    fields = FULL_FIELDS if args.full else POSTING_FIELDS
    rows = [{k: r[k] for k in fields} for r in rows[:args.limit]]
    _emit(rows, args.json, _table(rows, ["fit_level", "score", "company", "title", "deadline", "apply_url"])
          if rows else "(no postings)")


def _progress_line(company: str, s) -> str:
    if s.status == "done":
        return f"{company}: done fetched={s.fetched} new={s.new} stored={s.stored}"
    return f"{company}: {s.status}" + (f" {s.error}" if s.error else "")


def _report(job: Job, seen: dict[str, str]) -> None:
    for c, s in job.companies.items():
        line = _progress_line(c, s)
        if s.status != "pending" and seen.get(c) != line:
            seen[c] = line
            print(line, file=sys.stderr, flush=True)


async def _progress(jobs: JobManager, seen: dict[str, str]) -> None:
    while True:
        if jobs.current:
            _report(jobs.current, seen)
        await asyncio.sleep(PROGRESS_S)


async def _run_scrape(jobs: JobManager, companies: list[str] | None) -> Job:
    targets = await jobs.prepare(companies)
    seen: dict[str, str] = {}
    progress = asyncio.create_task(_progress(jobs, seen))
    try:
        job = await jobs.run(targets)
    finally:
        progress.cancel()
    _report(job, seen)
    return job


def _scrape(args: argparse.Namespace) -> None:
    env = _env()
    with closing(env.repo()) as repo:
        jobs = env.jobs(repo)
        try:
            job = asyncio.run(_run_scrape(jobs, args.companies or None))
        except KeyboardInterrupt:
            job = jobs.current
            if job and job.status == "running":  # _run이 시작되기 전에 취소된 경우
                job.status, job.finished_at = "interrupted", now_iso()
            _fail("interrupted", "중단됨 (Ctrl+C)", 130, job=job and job.to_dict())
        except LoginRequired as e:
            _fail("login_required", e.message, 3, login_command=e.login_command)
        except NoTargets as e:
            _fail("no_targets", str(e))
        except JobRunning as e:
            _fail("job_running", str(e))
    failed = [{"company": c, "error": s.error} for c, s in job.companies.items() if s.status == "failed"]
    if job.error:
        _fail("profile_failed", job.error, job=job.to_dict())
    if job.status == "auth_required":
        e = LoginRequired(job.provider)  # 선체크와 같은 message·login_command
        _fail("login_required", e.message, 3, login_command=e.login_command, job=job.to_dict())
    if len(failed) == len(job.companies):
        _fail("all_failed", "모든 회사가 실패했습니다.", job=job.to_dict())
    for f in failed:
        print(f"warning: {f['company']} failed: {f['error']}", file=sys.stderr)
    _emit({**job.to_dict(), "failed": failed}, args.json, "\n".join(
        _progress_line(c, s) for c, s in job.companies.items()))


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

    cmd("status", _status, "온보딩·마지막 성공 실행·stale·job_running")
    cmd("scrape", _scrape, "관심회사(또는 지정 회사) 스크래핑·판정 (동기, 진행은 stderr)").add_argument(
        "companies", nargs="*")
    ps = cmd("postings", _postings, "저장된 공고 (숨김 제외·관심회사만·score 내림차순)")
    ps.add_argument("--min-level", choices=list(LEVEL_RANK))
    ps.add_argument("--company", action="append", help="여러 번 지정 가능")
    ps.add_argument("--since", type=_since_arg, help="scraped_at 기준 (24h, 7d)")
    ps.add_argument("--limit", type=int)
    ps.add_argument("--full", action="store_true", help="summary, gaps 포함")
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
