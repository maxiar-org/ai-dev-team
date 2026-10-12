from dispatcher.models import ActiveTask, Item, engine_from_labels, item_key


def test_keys_identify_repo_and_number():
    item = Item("qr", 3, "issue", "T", "", frozenset())
    task = ActiveTask("qr", 3, "issue", "dev", "codex", "label", "c1", 0.0, "/p")
    assert item.key == task.key == item_key("qr", 3) == "qr#3"


def test_engine_from_labels_knows_gemini_and_has_no_default():
    assert engine_from_labels(frozenset({"engine:gemini"}), None) == "gemini"
    assert engine_from_labels(frozenset(), None) is None
    assert engine_from_labels(frozenset({"engine:codex", "engine:claude"}), None) == "claude"


def test_engines():
    assert engine_from_labels(frozenset({"engine:claude"}), "codex") == "claude"
    assert engine_from_labels(frozenset({"engine:codex"}), "claude") == "codex"
    assert engine_from_labels(frozenset(), "codex") == "codex"
