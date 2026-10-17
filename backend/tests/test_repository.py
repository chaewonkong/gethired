from app.repository import Repository


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
