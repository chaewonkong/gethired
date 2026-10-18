import json
import sqlite3
from datetime import datetime, timezone
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
    deleted_at TEXT,
    UNIQUE (company, external_id)
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


_fixed_now: str | None = None


def set_fixed_now(iso: str | None) -> None:
    global _fixed_now
    _fixed_now = iso


def now_iso() -> str:
    if _fixed_now is not None:
        return _fixed_now
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for k in ("tech_stack", "gaps"):
        if k in d:
            d[k] = json.loads(d[k])
    for k in ("bookmarked", "hidden"):
        if k in d:
            d[k] = bool(d[k])
    return d


class Repository:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- postings ---
    def upsert_postings(self, rows: list[dict[str, Any]]) -> None:
        self.conn.executemany(
            """INSERT INTO postings (company, external_id, title, summary, tech_stack, fit_level, score, gaps,
                                     fit_reason, apply_url, deadline, category, scraped_at, deleted_at)
               VALUES (:company, :external_id, :title, :summary, :tech_stack, :fit_level, :score, :gaps,
                       :fit_reason, :apply_url, :deadline, :category, :scraped_at, NULL)
               ON CONFLICT (company, external_id) DO UPDATE SET
                 title=excluded.title, summary=excluded.summary, tech_stack=excluded.tech_stack,
                 fit_level=excluded.fit_level, score=excluded.score, gaps=excluded.gaps,
                 fit_reason=excluded.fit_reason, apply_url=excluded.apply_url, deadline=excluded.deadline,
                 category=excluded.category, scraped_at=excluded.scraped_at, deleted_at=NULL""",
            [{**r, "tech_stack": json.dumps(r["tech_stack"], ensure_ascii=False),
              "gaps": json.dumps(r["gaps"], ensure_ascii=False)} for r in rows],
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
                      include_deleted: bool = False) -> list[dict[str, Any]]:
        where, params = [], []
        if not include_deleted:
            where.append("p.deleted_at IS NULL")
        if company:
            where.append("company=?")
            params.append(company)
        if min_level:
            levels = [lv for lv, rank in LEVEL_RANK.items() if rank >= LEVEL_RANK[min_level]]
            where.append(f"fit_level IN ({','.join('?' * len(levels))})")
            params += levels
        sql = ("SELECT p.*, b.posting_id IS NOT NULL AS bookmarked, h.posting_id IS NOT NULL AS hidden"
               " FROM postings p"
               " LEFT JOIN bookmarks b ON b.posting_id = p.id AND b.deleted_at IS NULL"
               " LEFT JOIN hides h ON h.posting_id = p.id AND h.deleted_at IS NULL"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.score DESC, p.id")
        return [_row(r) for r in self.conn.execute(sql, params).fetchall()]

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
        return {r["external_id"] for r in self.conn.execute(
            "SELECT external_id FROM judgments WHERE company=?", (company,)).fetchall()}

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

    # --- profile cache ---
    def get_profile_cache(self, hash_: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT profile FROM profile_cache WHERE hash=?", (hash_,)).fetchone()
        return json.loads(r["profile"]) if r else None

    def set_profile_cache(self, hash_: str, profile: dict[str, Any], now: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO profile_cache (hash, profile, created_at) VALUES (?, ?, ?)",
                          (hash_, json.dumps(profile, ensure_ascii=False), now))
        self.conn.commit()

    # --- settings ---
    def get_setting(self, key: str) -> str | None:
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set_setting(self, key: str, value: str, now: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                          (key, value, now))
        self.conn.commit()
