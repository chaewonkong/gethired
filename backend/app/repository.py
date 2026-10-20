import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

LEVEL_RANK = {"stretch": 1, "good": 2, "strong": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    tech_stack TEXT NOT NULL,
    fit_level TEXT NOT NULL,
    score INTEGER NOT NULL,
    gaps TEXT NOT NULL,
    fit_reason TEXT NOT NULL,
    apply_url TEXT NOT NULL,
    deadline TEXT,
    category TEXT,
    scraped_at TEXT NOT NULL,
    first_seen_at TEXT,
    deleted_at TEXT,
    description TEXT,
    requirements TEXT,
    preferred TEXT,
    breakdown TEXT,
    UNIQUE (company, external_id)
);
CREATE TABLE IF NOT EXISTS feedbacks (
    posting_id INTEGER NOT NULL REFERENCES postings(id),
    profile_hash TEXT NOT NULL,
    items TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (posting_id, profile_hash)
);
CREATE TABLE IF NOT EXISTS judgments (
    company TEXT NOT NULL,
    external_id TEXT NOT NULL,
    judged_at TEXT NOT NULL,
    stored INTEGER NOT NULL,
    PRIMARY KEY (company, external_id)
);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT,
    fetched_count INTEGER
);
CREATE TABLE IF NOT EXISTS bookmarks (
    posting_id INTEGER PRIMARY KEY REFERENCES postings(id),
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS hides (
    posting_id INTEGER PRIMARY KEY REFERENCES postings(id),
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS interests (
    company TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_cache (
    hash TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


_SELECT_POSTINGS = ("SELECT p.*, b.posting_id IS NOT NULL AS bookmarked, h.posting_id IS NOT NULL AS hidden"
                    " FROM postings p"
                    " LEFT JOIN bookmarks b ON b.posting_id = p.id AND b.deleted_at IS NULL"
                    " LEFT JOIN hides h ON h.posting_id = p.id AND h.deleted_at IS NULL")

_fixed_now: str | None = None


def set_fixed_now(iso: str | None) -> None:
    global _fixed_now
    _fixed_now = iso


def now_iso() -> str:
    if _fixed_now is not None:
        return _fixed_now
    return datetime.now(UTC).isoformat(timespec="seconds")


def _dt(iso: str) -> datetime:
    d = datetime.fromisoformat(iso)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


POSTING_COLUMNS_0014 = ("description", "requirements", "preferred", "breakdown")  # spec 0014에서 추가. 기존 행은 NULL
JSON_COLUMNS = ("tech_stack", "gaps", "requirements", "preferred", "breakdown")


def _row(r: sqlite3.Row, keep_description: bool = False) -> dict[str, Any]:
    """readonly 옛 DB에는 0014 컬럼이 없을 수 있다. 키가 없으면 건드리지 않고, 소비자는 .get()으로 읽는다"""
    d = dict(r)
    for k in JSON_COLUMNS:
        if d.get(k) is not None:
            d[k] = json.loads(d[k])
    for k in ("requirements", "preferred"):  # 0.5.0 개발 중 문자열로 저장된 행 → {text, fit: None}
        if d.get(k):
            d[k] = [{"text": x, "fit": None} if isinstance(x, str) else x for x in d[k]]
    for k in ("bookmarked", "hidden"):
        if k in d:
            d[k] = bool(d[k])
    if not keep_description:
        d.pop("description", None)  # 목록 응답 크기. SELECT는 p.*를 유지한다 (명시 컬럼은 옛 DB에서 no such column)
    return d


def _dump(r: dict[str, Any]) -> dict[str, Any]:
    out = {**{k: None for k in POSTING_COLUMNS_0014}, **r}
    for k in JSON_COLUMNS:
        if out.get(k) is not None:
            out[k] = json.dumps(out[k], ensure_ascii=False)
    return out


class Repository:
    def __init__(self, path: str | Path = ":memory:", readonly: bool = False):
        self.path = path
        if readonly:
            # 스키마를 만들지 않고 파일도 만들지 않는다 (쓰기 불가 디렉토리에서도 읽기)
            if not Path(path).is_file():
                raise FileNotFoundError(path)
            self.conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            return
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(postings)")}
        if "first_seen_at" not in cols:
            self.conn.execute("ALTER TABLE postings ADD COLUMN first_seen_at TEXT")
            self.conn.execute("UPDATE postings SET first_seen_at=scraped_at")
        for col in POSTING_COLUMNS_0014:
            if col not in cols:
                self.conn.execute(f"ALTER TABLE postings ADD COLUMN {col} TEXT")  # 기존 행은 NULL → 다음 스크래핑에서 재판정
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- postings ---
    def upsert_postings(self, rows: list[dict[str, Any]]) -> None:
        self.conn.executemany(
            """INSERT INTO postings (company, external_id, title, summary, tech_stack, fit_level, score, gaps,
                                     fit_reason, apply_url, deadline, category, scraped_at, first_seen_at, deleted_at,
                                     description, requirements, preferred, breakdown)
               VALUES (:company, :external_id, :title, :summary, :tech_stack, :fit_level, :score, :gaps,
                       :fit_reason, :apply_url, :deadline, :category, :scraped_at, :scraped_at, NULL,
                       :description, :requirements, :preferred, :breakdown)
               ON CONFLICT (company, external_id) DO UPDATE SET
                 title=excluded.title, summary=excluded.summary, tech_stack=excluded.tech_stack,
                 fit_level=excluded.fit_level, score=excluded.score, gaps=excluded.gaps,
                 fit_reason=excluded.fit_reason, apply_url=excluded.apply_url, deadline=excluded.deadline,
                 category=excluded.category, scraped_at=excluded.scraped_at, deleted_at=NULL,
                 description=excluded.description, requirements=excluded.requirements,
                 preferred=excluded.preferred, breakdown=excluded.breakdown""",
            [_dump(r) for r in rows],
        )
        self.conn.commit()

    def mark_seen(self, company: str, external_ids: set[str], now: str) -> None:
        """이번 스크랩에 다시 나타난 공고: 최근 스크래핑 일자 갱신, soft delete 해제"""
        self.conn.executemany(
            "UPDATE postings SET scraped_at=?, deleted_at=NULL WHERE company=? AND external_id=?",
            [(now, company, eid) for eid in external_ids],
        )
        self.conn.commit()

    def soft_delete_missing(self, company: str, external_ids: set[str], now: str) -> int:
        rows = self.conn.execute(
            "SELECT external_id FROM postings WHERE company=? AND deleted_at IS NULL", (company,)
        ).fetchall()
        gone = [r["external_id"] for r in rows if r["external_id"] not in external_ids]
        self.conn.executemany(
            "UPDATE postings SET deleted_at=? WHERE company=? AND external_id=?",
            [(now, company, eid) for eid in gone],
        )
        self.conn.commit()
        return len(gone)

    def list_postings(self, company: str | None = None, min_level: str | None = None,
                      include_deleted: bool = False, include_hidden: bool = True, interests_only: bool = False,
                      since: str | None = None) -> list[dict[str, Any]]:
        where, params = [], []
        if not include_deleted:
            where.append("p.deleted_at IS NULL")
        if not include_hidden:
            where.append("h.posting_id IS NULL")
        if interests_only:
            where.append("p.company IN (SELECT company FROM interests)")
        if company:
            where.append("p.company=?")
            params.append(company)
        if min_level:
            levels = [lv for lv, rank in LEVEL_RANK.items() if rank >= LEVEL_RANK[min_level]]
            where.append(f"fit_level IN ({','.join('?' * len(levels))})")
            params += levels
        sql = (_SELECT_POSTINGS + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.score DESC, p.id")
        rows = [_row(r) for r in self.conn.execute(sql, params).fetchall()]
        if since:  # 오프셋이 섞일 수 있어 문자열 비교 대신 시각으로
            # readonly는 마이그레이션 전 DB일 수 있어 scraped_at으로 대체
            rows = [r for r in rows if _dt(r.get("first_seen_at") or r["scraped_at"]) >= _dt(since)]
        return rows

    def get_posting(self, posting_id: int) -> dict[str, Any] | None:
        """상세 1건. description 포함. 삭제된 공고는 None, 숨김은 반환"""
        r = self.conn.execute(_SELECT_POSTINGS + " WHERE p.id=? AND p.deleted_at IS NULL", (posting_id,)).fetchone()
        return _row(r, keep_description=True) if r else None

    def delete_postings(self, company: str, external_ids: set[str]) -> int:
        """hard delete. 재판정에서 exclude로 바뀐 공고용 (soft delete는 mark_seen이 되살린다). 북마크·숨김·피드백도 함께"""
        if not external_ids:
            return 0
        marks = ",".join("?" * len(external_ids))
        ids = [r["id"] for r in self.conn.execute(
            f"SELECT id FROM postings WHERE company=? AND external_id IN ({marks})", (company, *external_ids))]
        if not ids:
            return 0
        id_marks = ",".join("?" * len(ids))
        for table in ("bookmarks", "hides", "feedbacks"):
            self.conn.execute(f"DELETE FROM {table} WHERE posting_id IN ({id_marks})", ids)
        self.conn.execute(f"DELETE FROM postings WHERE id IN ({id_marks})", ids)
        self.conn.commit()
        return len(ids)

    # --- bookmarks ---
    # 공고 soft delete 시 북마크는 JOIN에서 공고와 함께 숨겨지고, 공고가 다시 나타나면 함께 복구된다.
    # bookmarks.deleted_at은 사용자가 해제한 경우에만 쓴다.
    def set_bookmark(self, posting_id: int, on: bool, now: str) -> bool:
        """활성 공고가 없으면 False"""
        if not self.conn.execute("SELECT 1 FROM postings WHERE id=? AND deleted_at IS NULL", (posting_id,)).fetchone():
            return False
        if on:
            self.conn.execute(
                """INSERT INTO bookmarks (posting_id, created_at) VALUES (?, ?)
                   ON CONFLICT (posting_id) DO UPDATE SET created_at=excluded.created_at, deleted_at=NULL
                   WHERE bookmarks.deleted_at IS NOT NULL""", (posting_id, now))
        else:
            self.conn.execute("UPDATE bookmarks SET deleted_at=? WHERE posting_id=? AND deleted_at IS NULL",
                              (now, posting_id))
        self.conn.commit()
        return True

    def get_bookmark(self, posting_id: int) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM bookmarks WHERE posting_id=?", (posting_id,)).fetchone()
        return dict(r) if r else None

    # --- hides ---
    # 북마크와 같은 규칙: 공고 soft delete 시 JOIN에서 함께 숨겨지고, hides.deleted_at은 사용자 해제에만 쓴다.
    def set_hidden(self, posting_id: int, on: bool, now: str) -> bool:
        """활성 공고가 없으면 False"""
        if not self.conn.execute("SELECT 1 FROM postings WHERE id=? AND deleted_at IS NULL", (posting_id,)).fetchone():
            return False
        if on:
            self.conn.execute(
                """INSERT INTO hides (posting_id, created_at) VALUES (?, ?)
                   ON CONFLICT (posting_id) DO UPDATE SET created_at=excluded.created_at, deleted_at=NULL
                   WHERE hides.deleted_at IS NOT NULL""", (posting_id, now))
        else:
            self.conn.execute("UPDATE hides SET deleted_at=? WHERE posting_id=? AND deleted_at IS NULL",
                              (now, posting_id))
        self.conn.commit()
        return True

    def get_hidden(self, posting_id: int) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM hides WHERE posting_id=?", (posting_id,)).fetchone()
        return dict(r) if r else None

    # --- interests ---
    # 관심회사 해제는 이 테이블에서만 지운다. 공고·판정은 그대로 둔다
    def list_interests(self) -> list[str]:
        return [r["company"] for r in self.conn.execute("SELECT company FROM interests ORDER BY company").fetchall()]

    def set_interests(self, companies: list[str], now: str) -> None:
        self.conn.execute("DELETE FROM interests")
        self.conn.executemany("INSERT INTO interests (company, created_at) VALUES (?, ?)",
                              [(c, now) for c in dict.fromkeys(companies)])
        self.conn.commit()

    def set_interest(self, company: str, on: bool, now: str) -> None:
        if on:
            self.conn.execute("INSERT OR IGNORE INTO interests (company, created_at) VALUES (?, ?)", (company, now))
        else:
            self.conn.execute("DELETE FROM interests WHERE company=?", (company,))
        self.conn.commit()

    # --- judgments ---
    def judged_ids(self, company: str) -> set[str]:
        """저장됐는데 breakdown이 없는(0014 이전) 공고는 제외 → 다음 스크래핑에서 재판정. exclude는 그대로 judged"""
        return {r["external_id"] for r in self.conn.execute(
            """SELECT j.external_id FROM judgments j
               LEFT JOIN postings p ON p.company = j.company AND p.external_id = j.external_id
               WHERE j.company=? AND NOT (j.stored = 1 AND p.id IS NOT NULL AND p.breakdown IS NULL)""",
            (company,)).fetchall()}

    def record_judgments(self, company: str, external_ids: list[str], stored_ids: set[str], now: str) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO judgments (company, external_id, judged_at, stored) VALUES (?, ?, ?, ?)",
            [(company, eid, now, int(eid in stored_ids)) for eid in external_ids],
        )
        self.conn.commit()

    # --- scrape runs ---
    def start_run(self, company: str, now: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO scrape_runs (company, started_at, status) VALUES (?, ?, 'running')", (company, now))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, now: str, error: str | None = None,
                   fetched_count: int | None = None) -> None:
        self.conn.execute(
            "UPDATE scrape_runs SET status=?, finished_at=?, error=?, fetched_count=? WHERE id=?",
            (status, now, error, fetched_count, run_id))
        self.conn.commit()

    def last_runs(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT r.* FROM scrape_runs r
               JOIN (SELECT company, MAX(id) AS id FROM scrape_runs GROUP BY company) m ON m.id = r.id"""
        ).fetchall()
        return {r["company"]: dict(r) for r in rows}

    def last_success_runs(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT r.* FROM scrape_runs r
               JOIN (SELECT company, MAX(id) AS id FROM scrape_runs WHERE status='done' GROUP BY company) m
                 ON m.id = r.id"""
        ).fetchall()
        return {r["company"]: dict(r) for r in rows}

    def stale(self, companies: list[str], now: str, hours: float = 24) -> bool:
        """하나라도 마지막 성공 실행이 없거나 hours 초과"""
        last = self.last_success_runs()
        limit = _dt(now) - timedelta(hours=hours)
        return any(c not in last or _dt(last[c]["finished_at"]) < limit for c in companies)

    # --- profile cache ---
    def get_profile_cache(self, hash_: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT profile FROM profile_cache WHERE hash=?", (hash_,)).fetchone()
        return json.loads(r["profile"]) if r else None

    def set_profile_cache(self, hash_: str, profile: dict[str, Any], now: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO profile_cache (hash, profile, created_at) VALUES (?, ?, ?)",
                          (hash_, json.dumps(profile, ensure_ascii=False), now))
        self.conn.commit()

    # --- feedbacks ---
    def set_feedback(self, posting_id: int, profile_hash: str, items: list[str], now: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO feedbacks (posting_id, profile_hash, items, created_at) VALUES (?, ?, ?, ?)",
            (posting_id, profile_hash, json.dumps(items, ensure_ascii=False), now))
        self.conn.commit()

    def feedback_for(self, posting_id: int, current_hash: str) -> dict[str, Any] | None:
        """현재 프로필 피드백이 있으면 current=True. 없고 이전 프로필 것이 있으면 최근 것에 current=False. readonly 옛 DB(테이블 없음)는 None"""
        if not self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feedbacks'").fetchone():
            return None
        r = self.conn.execute(
            """SELECT items, created_at, profile_hash = ? AS current FROM feedbacks WHERE posting_id=?
               ORDER BY current DESC, created_at DESC LIMIT 1""", (current_hash, posting_id)).fetchone()
        return {"items": json.loads(r["items"]), "created_at": r["created_at"], "current": bool(r["current"])} if r else None

    # --- settings ---
    def get_setting(self, key: str) -> str | None:
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set_setting(self, key: str, value: str, now: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                          (key, value, now))
        self.conn.commit()
