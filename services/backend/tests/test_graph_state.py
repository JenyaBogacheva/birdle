"""Tests for graph state schema + in-memory session store."""

from services.backend.app.graph.state import SessionStore


class TestSessionStore:
    def test_create_returns_unique_ids(self):
        store = SessionStore(ttl_seconds=1800)
        a = store.create()
        b = store.create()
        assert a != b
        assert store.exists(a)
        assert store.exists(b)

    def test_touch_marks_known_session(self):
        store = SessionStore(ttl_seconds=1800)
        sid = store.create()
        assert store.touch(sid) is True
        assert store.touch("does-not-exist") is False

    def test_unknown_session_not_exists(self):
        store = SessionStore(ttl_seconds=1800)
        assert store.exists("nope") is False

    def test_eviction_of_expired(self):
        store = SessionStore(ttl_seconds=1800)
        sid = store.create(now=1000.0)
        # 1800s later, still alive; 1801s later, expired
        assert store.exists(sid, now=1000.0 + 1800) is True
        assert store.exists(sid, now=1000.0 + 1801) is False

    def test_sweep_removes_expired(self):
        store = SessionStore(ttl_seconds=10)
        sid = store.create(now=0.0)
        store.create(now=100.0)  # fresh
        removed = store.sweep(now=100.0)
        assert sid in removed
        assert store.exists(sid, now=100.0) is False


def test_bird_state_is_typeddict_with_expected_keys():
    from services.backend.app.graph.state import BirdState

    # TypedDict exposes declared keys via __annotations__
    keys = set(BirdState.__annotations__)
    assert {
        "messages",
        "description",
        "location",
        "observed_at",
        "region",
        "observed_window",
        "ask_rounds",
        "final",
    } <= keys
