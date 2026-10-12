import pytest

from dispatcher.models import Slot
from dispatcher.routing import LONG_EXHAUSTION_S, choose_slot, preferences, task_size

SLOTS = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))
NOW = 1000.0


def L(*labels):
    return frozenset(labels)


def test_size_defaults_to_m():
    assert task_size(L()) == "M" and task_size(L("size:L")) == "L" and task_size(L("size:S")) == "S"


@pytest.mark.parametrize("labels,expected", [
    (L("size:L"), (("claude", "codex"), True)),
    (L("kind:architecture", "size:S"), (("claude", "codex"), True)),
    (L("size:M"), (("codex", "gemini", "claude"), True)),
    (L(), (("codex", "gemini", "claude"), True)),
    (L("needs:images"), (("codex", "gemini"), True)),
    (L("engine:gemini", "size:L"), (("gemini",), True)),
])
def test_dev_preferences(labels, expected):
    assert preferences("dev", labels, "issue") == expected


def test_docs_preferences_do_not_wait():
    assert preferences("docs", L(), "issue") == (("codex", "gemini", "claude"), False)


@pytest.mark.parametrize("labels,expected", [
    (L("engine:codex"), ("claude",)),
    (L("engine:gemini"), ("claude", "codex")),
    (L("engine:claude"), ("codex",)),
    (L("engine:claude", "engine:codex"), ()),
    (L(), ("claude",)),
])
def test_review_never_uses_the_dev_engine_and_gemini_does_not_review(labels, expected):
    assert preferences("review", labels, "pr") == (expected, False)


def test_qa_prefers_gemini():
    assert preferences("qa", L("engine:codex"), "pr") == (("gemini", "codex", "claude"), False)


def test_fix_prefers_the_dev_engine():
    assert preferences("fix", L("engine:claude"), "pr") == (("claude", "codex", "gemini"), False)
    assert preferences("fix", L(), "pr") == (("codex", "claude", "gemini"), False)


def test_choose_free_preferred_slot():
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), {}, NOW).name == "codex-senior"


def test_dev_waits_while_preferred_is_busy():
    assert choose_slot(("codex", "gemini"), True, SLOTS, {"codex-senior"}, {}, NOW) is None


def test_non_waiting_task_uses_fallback_when_busy():
    assert choose_slot(("gemini", "codex"), False, SLOTS, {"gemini"}, {}, NOW).name == "codex-senior"


def test_dev_waits_for_short_exhaustion_but_moves_on_long_one():
    short = {"codex-senior": NOW + LONG_EXHAUSTION_S - 1}
    long = {"codex-senior": NOW + LONG_EXHAUSTION_S + 1}
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), short, NOW) is None
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), long, NOW).name == "gemini"


def test_expired_exhaustion_is_ignored():
    assert choose_slot(("codex",), True, SLOTS, set(), {"codex-senior": NOW - 1}, NOW).name == "codex-senior"


def test_forced_engine_never_falls_back():
    assert choose_slot(("gemini",), True, SLOTS, set(), {"gemini": NOW + 99999}, NOW) is None


def test_engines_without_slots_are_skipped():
    two = SLOTS[:2]
    assert choose_slot(("gemini", "codex"), False, two, set(), {}, NOW).name == "codex-senior"
