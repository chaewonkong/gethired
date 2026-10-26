import os
import re
import sqlite3

import pytest

from app.repository import SCHEMA, Repository


def row(company="toss", eid="1", **kw):
    base = {"company": company, "external_id": eid, "title": f"job {eid}", "summary": "s" * 10,
            "tech_stack": ["Go"], "fit_level": "good", "score": 70, "gaps": [], "fit_reason": "r" * 20,
            "apply_url": "https://x/1", "deadline": None, "category": "Backend", "scraped_at": "2026-10-09T00:00:00"}
    return {**base, **kw}


def test_upsert_and_list_order_and_filters():
    repo = Repository()
    repo.upsert_postings([row(eid="a", score=50, fit_level="stretch"), row(eid="b", score=90, fit_level="strong"),
                          row(company="naver", eid="c", score=70)])
    ids = [p["external_id"] for p in repo.list_postings()]
    assert ids == ["b", "c", "a"]
    assert [p["external_id"] for p in repo.list_postings(company="toss")] == ["b", "a"]
    assert [p["external_id"] for p in repo.list_postings(min_level="good")] == ["b", "c"]
    assert repo.list_postings()[0]["tech_stack"] == ["Go"]


def test_upsert_updates_existing_and_undeletes():
    repo = Repository()
    repo.upsert_postings([row(eid="a", score=50)])
    repo.soft_delete_missing("toss", set(), "T1")
    assert repo.list_postings() == []
    repo.upsert_postings([row(eid="a", score=88, fit_level="strong")])
    got = repo.list_postings()
    assert len(got) == 1 and got[0]["score"] == 88 and got[0]["deleted_at"] is None


def test_soft_delete_and_mark_seen_cycle():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b"), row(company="naver", eid="n")])
    deleted = repo.soft_delete_missing("toss", {"a"}, "T1")
    assert deleted == 1
    assert {p["external_id"] for p in repo.list_postings()} == {"a", "n"}
    assert {p["external_id"] for p in repo.list_postings(include_deleted=True)} == {"a", "b", "n"}
    repo.mark_seen("toss", {"b"}, "T2")
    b = next(p for p in repo.list_postings() if p["external_id"] == "b")
    assert b["deleted_at"] is None and b["scraped_at"] == "T2"


def test_first_seen_at_kept_across_upsert_and_mark_seen():
    repo = Repository()
    repo.upsert_postings([row(eid="a", scraped_at="T1")])
    repo.mark_seen("toss", {"a"}, "T2")
    repo.upsert_postings([row(eid="a", scraped_at="T3", score=90)])
    a = repo.list_postings()[0]
    assert a["first_seen_at"] == "T1" and a["scraped_at"] == "T3"


def old_db(path, scraped_at="2026-10-09T00:00:00+00:00"):
    """first_seen_at 추가 전 스키마의 DB"""
    assert "    first_seen_at TEXT,\n" in SCHEMA
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.replace("    first_seen_at TEXT,\n", ""))
    conn.execute("""INSERT INTO postings (company, external_id, title, summary, tech_stack, fit_level, score, gaps,
                                          fit_reason, apply_url, scraped_at)
                    VALUES ('toss', 'a', 't', 's', '[]', 'good', 70, '[]', 'r', 'u', ?)""", (scraped_at,))
    conn.commit()
    conn.close()


def test_migrate_adds_first_seen_at_from_scraped_at(tmp_path):
    db = tmp_path / "old.db"
    old_db(db, scraped_at="T1")
    repo = Repository(db)
    assert repo.list_postings()[0]["first_seen_at"] == "T1"
    repo.close()
    assert Repository(db).list_postings()[0]["first_seen_at"] == "T1"


def test_readonly_since_falls_back_to_scraped_at_before_migration(tmp_path):
    db = tmp_path / "old.db"
    old_db(db, scraped_at="2026-10-10T00:00:00+00:00")
    ro = Repository(db, readonly=True)
    assert "first_seen_at" not in ro.list_postings()[0]
    assert [p["external_id"] for p in ro.list_postings(since="2026-10-09T00:00:00+00:00")] == ["a"]
    assert ro.list_postings(since="2026-10-11T00:00:00+00:00") == []


def test_judgments_and_runs_and_profile_cache():
    repo = Repository()
    repo.record_judgments("toss", ["a", "b"], {"a"}, "T1")
    assert repo.judged_ids("toss") == {"a", "b"}
    assert repo.judged_ids("naver") == set()

    rid = repo.start_run("toss", "T1")
    repo.finish_run(rid, "done", "T2", fetched_count=5)
    rid2 = repo.start_run("toss", "T3")
    repo.finish_run(rid2, "failed", "T4", error="boom")
    last = repo.last_runs()
    assert last["toss"]["status"] == "failed" and last["toss"]["error"] == "boom"

    assert repo.get_profile_cache("h") is None
    repo.set_profile_cache("h", {"name": "x"}, "T1")
    assert repo.get_profile_cache("h") == {"name": "x"}


def bookmarked(repo):
    return [p["external_id"] for p in repo.list_postings() if p["bookmarked"]]


def test_bookmark_insert_soft_delete_and_rebookmark():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b")])
    a = repo.list_postings()[0]["id"]
    assert bookmarked(repo) == []

    assert repo.set_bookmark(a, True, "T1")
    assert bookmarked(repo) == ["a"]
    assert repo.get_bookmark(a) == {"posting_id": a, "created_at": "T1", "deleted_at": None}

    repo.set_bookmark(a, True, "T2")
    assert repo.get_bookmark(a)["created_at"] == "T1"

    repo.set_bookmark(a, False, "T3")
    assert bookmarked(repo) == []
    assert repo.get_bookmark(a)["deleted_at"] == "T3"

    repo.set_bookmark(a, True, "T4")
    assert repo.get_bookmark(a) == {"posting_id": a, "created_at": "T4", "deleted_at": None}

    assert not repo.set_bookmark(9999, True, "T5")


def test_bookmark_hidden_with_deleted_posting_and_restored_when_posting_returns():
    repo = Repository()
    repo.upsert_postings([row(eid="a")])
    a = repo.list_postings()[0]["id"]
    repo.set_bookmark(a, True, "T1")

    repo.soft_delete_missing("toss", set(), "T2")
    assert repo.list_postings() == []
    assert not repo.set_bookmark(a, False, "T3")

    repo.mark_seen("toss", {"a"}, "T4")
    assert bookmarked(repo) == ["a"]
    assert repo.get_bookmark(a)["deleted_at"] is None


def hidden(repo):
    return [p["external_id"] for p in repo.list_postings() if p["hidden"]]


def test_hide_insert_soft_delete_and_rehide():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b")])
    a = repo.list_postings()[0]["id"]
    assert hidden(repo) == []

    assert repo.set_hidden(a, True, "T1")
    assert hidden(repo) == ["a"]
    assert repo.get_hidden(a) == {"posting_id": a, "created_at": "T1", "deleted_at": None}

    repo.set_hidden(a, True, "T2")
    assert repo.get_hidden(a)["created_at"] == "T1"

    repo.set_hidden(a, False, "T3")
    assert hidden(repo) == []
    assert repo.get_hidden(a)["deleted_at"] == "T3"

    repo.set_hidden(a, True, "T4")
    assert repo.get_hidden(a) == {"posting_id": a, "created_at": "T4", "deleted_at": None}

    assert not repo.set_hidden(9999, True, "T5")


def test_hide_independent_of_bookmark():
    repo = Repository()
    repo.upsert_postings([row(eid="a")])
    a = repo.list_postings()[0]["id"]
    repo.set_bookmark(a, True, "T1")
    repo.set_hidden(a, True, "T2")
    p = repo.list_postings()[0]
    assert p["bookmarked"] is True and p["hidden"] is True

    repo.set_hidden(a, False, "T3")
    p = repo.list_postings()[0]
    assert p["bookmarked"] is True and p["hidden"] is False


def test_hide_gone_with_deleted_posting_and_restored_when_posting_returns():
    repo = Repository()
    repo.upsert_postings([row(eid="a")])
    a = repo.list_postings()[0]["id"]
    repo.set_hidden(a, True, "T1")

    repo.soft_delete_missing("toss", set(), "T2")
    assert repo.list_postings() == []
    assert not repo.set_hidden(a, False, "T3")

    repo.mark_seen("toss", {"a"}, "T4")
    assert hidden(repo) == ["a"]
    assert repo.get_hidden(a)["deleted_at"] is None


def test_interests_set_and_toggle():
    repo = Repository()
    assert repo.list_interests() == []
    repo.set_interests(["toss", "naver", "toss"], "T1")
    assert repo.list_interests() == ["naver", "toss"]
    repo.set_interest("kakao", True, "T2")
    repo.set_interest("kakao", True, "T3")
    repo.set_interest("toss", False, "T4")
    assert repo.list_interests() == ["kakao", "naver"]
    repo.set_interests(["line"], "T5")
    assert repo.list_interests() == ["line"]


def test_settings_get_set_overwrite():
    repo = Repository()
    assert repo.get_setting("provider") is None
    repo.set_setting("provider", "claude", "T1")
    assert repo.get_setting("provider") == "claude"
    repo.set_setting("provider", "codex", "T2")
    assert repo.get_setting("provider") == "codex"
    assert repo.conn.execute("SELECT updated_at FROM settings WHERE key='provider'").fetchone()[0] == "T2"
    assert repo.get_setting("missing") is None


def test_list_postings_hidden_interests_since():
    repo = Repository()
    repo.upsert_postings([row(eid="a", score=90, scraped_at="2026-10-09T00:00:00+00:00"),
                          row(eid="b", score=80, scraped_at="2026-10-10T00:00:00+00:00"),
                          row(company="naver", eid="n", score=70, scraped_at="2026-10-10T09:00:00+09:00")])
    ids = {p["external_id"]: p["id"] for p in repo.list_postings()}
    repo.set_hidden(ids["b"], True, "T1")
    repo.set_interests(["toss"], "T1")

    assert [p["external_id"] for p in repo.list_postings()] == ["a", "b", "n"]
    assert [p["external_id"] for p in repo.list_postings(include_hidden=False)] == ["a", "n"]
    assert [p["external_id"] for p in repo.list_postings(interests_only=True)] == ["a", "b"]
    # n은 +09:00 오프셋이지만 같은 순간(2026-10-10T00:00Z)
    assert [p["external_id"] for p in repo.list_postings(since="2026-10-10T00:00:00+00:00")] == ["b", "n"]
    assert [p["external_id"] for p in repo.list_postings(include_hidden=False, interests_only=True,
                                                         since="2026-10-09T12:00:00+00:00")] == []
    # 다시 확인돼 scraped_at이 갱신돼도 since는 처음 수집 시각 기준
    repo.mark_seen("toss", {"a"}, "2026-10-11T00:00:00+00:00")
    assert [p["external_id"] for p in repo.list_postings(since="2026-10-10T00:00:00+00:00")] == ["b", "n"]


def test_last_success_runs_and_stale():
    repo = Repository()
    r1 = repo.start_run("toss", "2026-10-09T00:00:00+00:00")
    repo.finish_run(r1, "done", "2026-10-09T00:00:00+00:00", fetched_count=3)
    r2 = repo.start_run("toss", "2026-10-09T06:00:00+00:00")
    repo.finish_run(r2, "failed", "2026-10-09T06:00:00+00:00", error="boom")
    r3 = repo.start_run("naver", "2026-10-09T01:00:00+00:00")
    repo.finish_run(r3, "auth_required", "2026-10-09T01:00:00+00:00")

    last = repo.last_success_runs()
    assert set(last) == {"toss"} and last["toss"]["id"] == r1 and last["toss"]["fetched_count"] == 3
    assert repo.last_runs()["toss"]["status"] == "failed"

    assert repo.stale(["toss"], "2026-10-10T00:00:00+00:00") is False  # 정확히 24h
    assert repo.stale(["toss"], "2026-10-10T00:00:01+00:00") is True
    assert repo.stale(["toss"], "2026-10-10T09:00:00+09:00") is False
    assert repo.stale(["toss"], "2026-10-09T12:00:00+00:00", hours=6) is True
    assert repo.stale(["toss", "naver"], "2026-10-09T01:00:00+00:00") is True  # naver 성공 없음
    assert repo.stale([], "2026-10-10T00:00:00+00:00") is False


def test_readonly_reads_and_rejects_writes(tmp_path):
    path = tmp_path / "app.db"
    repo = Repository(path)
    repo.upsert_postings([row(eid="a")])
    repo.close()

    ro = Repository(path, readonly=True)
    assert [p["external_id"] for p in ro.list_postings()] == ["a"]
    with pytest.raises(sqlite3.OperationalError):
        ro.set_setting("provider", "codex", "T1")
    with pytest.raises(FileNotFoundError):
        Repository(tmp_path / "missing" / "app.db", readonly=True)
    assert not (tmp_path / "missing").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_readonly_in_unwritable_dir(tmp_path):
    d = tmp_path / "home"
    repo = Repository(d / "app.db")
    repo.upsert_postings([row(eid="a")])
    run = repo.start_run("toss", "2026-10-09T00:00:00+00:00")
    repo.finish_run(run, "done", "2026-10-09T00:00:00+00:00")
    repo.close()
    before = sorted(p.name for p in d.iterdir())
    os.chmod(d, 0o555)
    try:
        ro = Repository(d / "app.db", readonly=True)
        assert [p["external_id"] for p in ro.list_postings()] == ["a"]
        assert set(ro.last_success_runs()) == {"toss"}
        ro.close()
        assert sorted(p.name for p in d.iterdir()) == before
    finally:
        os.chmod(d, 0o755)


# --- spec 0014: 본문·breakdown·requirements·preferred, feedbacks, 재판정 ---
def old_db_0013(path):
    """0014 컬럼·feedbacks 테이블이 없는 0.4.0 스키마의 DB. readonly로 열면 마이그레이션이 돌지 않는다"""
    schema = SCHEMA
    for col in ("description", "requirements", "preferred", "breakdown"):
        assert f"    {col} TEXT,\n" in schema
        schema = schema.replace(f"    {col} TEXT,\n", "")
    schema, n = re.subn(r"CREATE TABLE IF NOT EXISTS feedbacks \(.*?\);\n", "", schema, flags=re.S)
    assert n == 1
    schema, n = re.subn(r"CREATE TABLE IF NOT EXISTS applications \(.*?\);\n", "", schema, flags=re.S)
    assert n == 1
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    conn.execute("""INSERT INTO postings (company, external_id, title, summary, tech_stack, fit_level, score, gaps,
                                          fit_reason, apply_url, scraped_at, first_seen_at)
                    VALUES ('toss', 'a', 't', 's', '[]', 'good', 70, '[]', 'r', 'u', 'T1', 'T1')""")
    conn.execute("INSERT INTO judgments (company, external_id, judged_at, stored) VALUES ('toss', 'a', 'T1', 1)")
    conn.commit()
    conn.close()


def test_migrate_adds_0014_columns_with_null(tmp_path):
    db = tmp_path / "old.db"
    old_db_0013(db)
    repo = Repository(db)
    cols = {r["name"] for r in repo.conn.execute("PRAGMA table_info(postings)")}
    assert {"description", "requirements", "preferred", "breakdown"} <= cols
    got = repo.list_postings()[0]
    assert got["breakdown"] is None and got["requirements"] is None and "description" not in got
    assert repo.get_posting(got["id"])["description"] is None
    assert repo.feedback_for(got["id"], "h") is None


def test_readonly_old_db_tolerates_missing_columns_and_table(tmp_path):
    db = tmp_path / "old.db"
    old_db_0013(db)
    ro = Repository(db, readonly=True)
    rows = ro.list_postings()
    assert len(rows) == 1 and "breakdown" not in rows[0] and "description" not in rows[0]
    assert rows[0]["application"] is None
    assert [r["id"] for r in ro.list_postings(include_applied=False, include_hidden=False)] == [rows[0]["id"]]
    detail = ro.get_posting(rows[0]["id"])
    assert detail["external_id"] == "a" and "breakdown" not in detail and detail["application"] is None
    assert ro.feedback_for(rows[0]["id"], "h") is None


def test_upsert_stores_and_reads_0014_fields():
    repo = Repository()
    bd = {"skills": 30, "domain": 25, "seniority": 10, "preferred": 5}
    req, pref = [{"text": "Go 3년", "fit": "met"}], [{"text": "k8s", "fit": "partial"}]
    repo.upsert_postings([row(eid="a", description="본문", requirements=req, preferred=pref, breakdown=bd)])
    listed = repo.list_postings()[0]
    assert listed["requirements"] == req and listed["preferred"] == pref and listed["breakdown"] == bd
    assert "description" not in listed
    detail = repo.get_posting(listed["id"])
    assert detail["description"] == "본문" and detail["bookmarked"] is False and detail["hidden"] is False
    repo.upsert_postings([row(eid="a", description="수정", requirements=[], preferred=[], breakdown=bd)])
    assert repo.get_posting(listed["id"])["description"] == "수정"
    repo.upsert_postings([row(eid="legacy")])  # 0014 키 없는 행도 저장된다 (None)
    assert repo.list_postings(company="toss")[1]["breakdown"] is None


def test_get_posting_none_for_deleted_but_returns_hidden():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b")])
    a, b = (p["id"] for p in repo.list_postings())
    repo.set_hidden(b, True, "T1")
    assert repo.get_posting(b)["hidden"] is True
    repo.soft_delete_missing("toss", {"b"}, "T2")
    assert repo.get_posting(a) is None
    assert repo.get_posting(9999) is None


def test_judged_ids_excludes_stored_without_breakdown():
    repo = Repository()
    bd = {"skills": 30, "domain": 25, "seniority": 10, "preferred": 5}
    repo.upsert_postings([row(eid="legacy"), row(eid="fresh", breakdown=bd)])
    repo.record_judgments("toss", ["legacy", "fresh", "excluded"], {"legacy", "fresh"}, "T1")
    assert repo.judged_ids("toss") == {"fresh", "excluded"}
    repo.upsert_postings([row(eid="legacy", breakdown=bd)])
    assert repo.judged_ids("toss") == {"legacy", "fresh", "excluded"}


def test_delete_postings_removes_bookmark_hide_feedback():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b"), row(company="naver", eid="a")])
    a = next(p["id"] for p in repo.list_postings() if p["company"] == "toss" and p["external_id"] == "a")
    repo.set_bookmark(a, True, "T1")
    repo.set_hidden(a, True, "T1")
    repo.set_feedback(a, "h", ["x: y"], "T1")
    repo.set_application(a, "T1")
    assert repo.delete_postings("toss", {"a", "missing"}) == 1
    assert repo.get_posting(a) is None and repo.get_bookmark(a) is None and repo.get_hidden(a) is None
    assert repo.get_application(a) is None
    assert repo.conn.execute("SELECT count(*) FROM feedbacks").fetchone()[0] == 0
    assert {(p["company"], p["external_id"]) for p in repo.list_postings()} == {("toss", "b"), ("naver", "a")}
    assert repo.delete_postings("toss", set()) == 0


def test_feedback_for_current_previous_none():
    repo = Repository()
    repo.upsert_postings([row(eid="a")])
    a = repo.list_postings()[0]["id"]
    assert repo.feedback_for(a, "h1") is None
    repo.set_feedback(a, "h0", ["old: 1"], "T0")
    assert repo.feedback_for(a, "h1") == {"items": ["old: 1"], "created_at": "T0", "current": False}
    repo.set_feedback(a, "h1", ["new: 1"], "T1")
    assert repo.feedback_for(a, "h1") == {"items": ["new: 1"], "created_at": "T1", "current": True}
    assert repo.feedback_for(a, "h2")["created_at"] == "T1"  # 다른 해시: 가장 최근 것, current False
    assert repo.feedback_for(a, "h2")["current"] is False
    repo.set_feedback(a, "h1", ["new: 2"], "T2")  # 같은 해시 덮어쓰기
    assert repo.feedback_for(a, "h1")["items"] == ["new: 2"]


def test_row_normalizes_string_requirements_to_objects():
    repo = Repository()
    repo.upsert_postings([row(eid="a", requirements=["문자열 요건"], preferred=[])])
    got = repo.list_postings()[0]
    assert got["requirements"] == [{"text": "문자열 요건", "fit": None}] and got["preferred"] == []


# --- spec 0015: 지원완료 ---
def applied(repo):
    return [p["external_id"] for p in repo.list_postings() if p["application"]]


def test_application_set_clear_reapply_and_idempotent():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b")])
    a = next(p["id"] for p in repo.list_postings() if p["external_id"] == "a")
    assert all(p["application"] is None for p in repo.list_postings())

    assert repo.set_application(a, "T1") == {"applied_at": "T1", "stage": None}
    assert repo.set_application(a, "T2") == {"applied_at": "T1", "stage": None}  # 멱등
    assert applied(repo) == ["a"]
    assert repo.get_posting(a)["application"] == {"applied_at": "T1", "stage": None}
    assert [p["external_id"] for p in repo.list_postings(include_applied=False)] == ["b"]

    assert repo.clear_application(a, "T3") is True
    assert applied(repo) == [] and repo.get_application(a)["deleted_at"] == "T3"
    assert repo.clear_application(a, "T4") is True  # 이미 해제여도 True
    assert repo.get_application(a)["deleted_at"] == "T3"

    assert repo.set_application(a, "T5") == {"applied_at": "T5", "stage": None}  # 재지원은 created_at 갱신
    assert repo.get_application(a)["updated_at"] == "T5"
    assert repo.set_application(9999, "T6") is None
    assert repo.clear_application(9999, "T6") is False


def test_applied_posting_survives_soft_delete_and_restores():
    repo = Repository()
    repo.upsert_postings([row(eid="a"), row(eid="b")])
    ids = {p["external_id"]: p["id"] for p in repo.list_postings()}
    repo.set_application(ids["a"], "T1")
    repo.set_bookmark(ids["b"], True, "T1")

    assert repo.soft_delete_missing("toss", set(), "T2") == 2
    rows = repo.list_postings()
    assert [(p["external_id"], p["deleted_at"]) for p in rows] == [("a", "T2")]  # 지원완료만 남는다
    assert rows[0]["application"]["applied_at"] == "T1"
    assert repo.get_posting(ids["a"])["deleted_at"] == "T2" and repo.get_posting(ids["b"]) is None
    assert repo.list_postings(include_applied=False) == []
    assert repo.set_application(ids["a"], "T3") is None  # 마감 공고는 새로 지원완료 불가
    assert repo.clear_application(ids["a"], "T3") is True  # 해제는 가능
    assert repo.list_postings() == [] and repo.get_posting(ids["a"]) is None

    assert repo.set_application(ids["a"], "T4") is None  # 해제된 마감 공고도 마찬가지
    repo.mark_seen("toss", {"a"}, "T5")
    assert repo.set_application(ids["a"], "T6") == {"applied_at": "T6", "stage": None}
    repo.soft_delete_missing("toss", set(), "T7")
    repo.mark_seen("toss", {"a"}, "T8")
    p = repo.get_posting(ids["a"])
    assert p["deleted_at"] is None and p["application"] == {"applied_at": "T6", "stage": None}
