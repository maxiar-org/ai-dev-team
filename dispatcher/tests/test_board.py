import pytest

from dispatcher.board import (
    BACKLOG,
    IN_PROGRESS,
    IN_REVIEW,
    NEEDS_HUMAN,
    READY,
    AddToBoard,
    SetColumn,
    column_for,
    plan_board,
)
from dispatcher.models import Item


def issue(n, *labels):
    return Item("qr", n, "issue", "T", "", frozenset(labels), node_id=f"I_{n}")


def pr(n, *labels):
    return Item("qr", n, "pr", "PR", "", frozenset(labels), "feature/x", node_id=f"PR_{n}")


@pytest.mark.parametrize(
    "item,column",
    [
        (issue(1), BACKLOG),
        (issue(1, "agent:dev"), READY),
        (issue(1, "agent:dev", "agent:working"), IN_PROGRESS),
        (pr(2), IN_REVIEW),
        (pr(2, "agent:review"), IN_REVIEW),
        (pr(2, "agent:working"), IN_PROGRESS),
        (issue(1, "agent:working", "needs:human"), NEEDS_HUMAN),
        (pr(2, "needs:human"), NEEDS_HUMAN),
    ],
)
def test_column_for(item, column):
    assert column_for(item) == column


def test_plan_board_adds_missing_items_and_fixes_stale_columns():
    items = [issue(1, "agent:dev"), issue(2), pr(3)]
    current = {"qr#2": ("PVTI_2", BACKLOG), "qr#3": ("PVTI_3", BACKLOG)}
    assert plan_board(items, current) == [
        AddToBoard(issue(1, "agent:dev"), READY),
        SetColumn("PVTI_3", "qr#3", IN_REVIEW),
    ]


def test_plan_board_sets_column_when_item_has_none():
    assert plan_board([issue(2)], {"qr#2": ("PVTI_2", None)}) == [SetColumn("PVTI_2", "qr#2", BACKLOG)]


def test_issue_with_open_pr_follows_its_pr_column():
    issue2 = issue(2)
    pr10 = Item("qr", 10, "pr", "PR", "Closes #2", frozenset({"needs:human"}), "agent/2-wa", node_id="PR_10")
    current = {"qr#2": ("PVTI_2", BACKLOG), "qr#10": ("PVTI_10", NEEDS_HUMAN)}
    assert plan_board([issue2, pr10], current) == [SetColumn("PVTI_2", "qr#2", NEEDS_HUMAN)]


def test_issue_with_open_pr_in_review_is_in_review():
    pr11 = Item("qr", 11, "pr", "PR", "", frozenset({"engine:codex"}), "agent/3-instagram", node_id="PR_11")
    assert plan_board([issue(3), pr11], {"qr#3": ("PVTI_3", BACKLOG), "qr#11": ("PVTI_11", IN_REVIEW)}) == [
        SetColumn("PVTI_3", "qr#3", IN_REVIEW)
    ]
