from dispatcher.models import ActiveTask, Item, engine_from_labels, item_key, other_engine


def test_keys_identify_repo_and_number():
    item = Item("qr", 3, "issue", "T", "", frozenset())
    task = ActiveTask("qr", 3, "issue", "dev", "codex", "label", "c1", 0.0, "/p")
    assert item.key == task.key == item_key("qr", 3) == "qr#3"


def test_engines():
    assert other_engine("codex") == "claude"
    assert other_engine("claude") == "codex"
    assert engine_from_labels(frozenset({"engine:claude"}), "codex") == "claude"
    assert engine_from_labels(frozenset({"engine:codex"}), "claude") == "codex"
    assert engine_from_labels(frozenset(), "codex") == "codex"
