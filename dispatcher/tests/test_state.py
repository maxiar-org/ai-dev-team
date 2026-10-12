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
        qa_rounds={"qr#12": 1},
        docs_only_notified={"ai-dev-team#3"},
    )
    store.save(state)
    assert store.load() == state
    assert not (tmp_path / "sub" / "s.tmp").exists()


def test_old_state_without_slots_loads(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"active": {"qr#1": {"repo": "qr", "number": 1, "kind": "issue", "role": "dev", "engine": "codex", '
                 '"trigger": "label", "conversation_id": "c", "started_at": 1.0, "workspace": "/w"}}}')
    state = StateStore(p).load()
    assert state.active["qr#1"].slot == "" and state.slot_exhausted_until == {}


def test_slot_exhaustion_round_trips(tmp_path):
    store = StateStore(tmp_path / "state.json")
    state = State(slot_exhausted_until={"codex-senior": 123.0})
    store.save(state)
    assert store.load().slot_exhausted_until == {"codex-senior": 123.0}
