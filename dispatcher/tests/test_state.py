from dispatcher.models import ActiveTask
from dispatcher.state import State, StateStore


def test_missing_file_gives_empty_state(tmp_path):
    assert StateStore(tmp_path / "s.json").load() == State()


def test_roundtrip_is_lossless_and_atomic(tmp_path):
    store = StateStore(tmp_path / "sub" / "s.json")
    task = ActiveTask("qr", 3, "issue", "dev", "codex", "label", "c1", 1.5, "/p")
    state = State(
        active={task.key: task},
        processed_comments={3, 1},
        review_rounds={"qr#7": 1},
        comments_since="2026-10-03T00:00:00+00:00",
        conflict_attempts={"qr#11": 1},
        blocked_notified={"qr#5": [4]},
    )
    store.save(state)
    assert store.load() == state
    assert not (tmp_path / "sub" / "s.tmp").exists()
