import pytest

from dispatcher.models import ActiveTask, AddLabels, Item, PostComment, RemoveLabel, RequestReview
from dispatcher.outcomes import find_pr_for_issue, outcome_for, parse_qa_verdict, parse_verdict


def task(role="dev", kind="issue", number=3, engine="codex", trigger="label"):
    return ActiveTask("qr", number, kind, role, engine, trigger, "conv-1", 0.0, "/p")


def pr_item(number=7, head="agent/3-whatsapp", body=""):
    return Item("qr", number, "pr", "PR", body, frozenset(), head)


def test_dev_with_pr_sends_it_to_review():
    out = outcome_for(task(), "finished", "listo", frozenset({"agent:working"}), pr_item(), 0, 2)
    assert out.result == "pr_abierto"
    assert out.ops == (
        RemoveLabel(3, "agent:working"),
        RemoveLabel(3, "agent:dev"),
        AddLabels(7, ("agent:review", "engine:codex")),
    )


def test_dev_that_asked_for_help_only_clears_working():
    out = outcome_for(task(), "finished", "", frozenset({"needs:human"}), None, 0, 2)
    assert (out.result, out.ops) == ("needs_human", (RemoveLabel(3, "agent:working"), RemoveLabel(3, "agent:dev")))


def test_dev_without_pr_or_question_escalates_with_last_answer():
    out = outcome_for(task(), "idle", "No encontré el archivo", frozenset(), None, 0, 2)
    assert out.result == "sin_resultado"
    assert AddLabels(3, ("needs:human",)) in out.ops
    [comment] = [op for op in out.ops if isinstance(op, PostComment)]
    assert "> No encontré el archivo" in comment.body


@pytest.mark.parametrize("status", ["error", "stuck", "timeout", "missing"])
def test_abnormal_status_escalates(status):
    out = outcome_for(task(), status, "", frozenset(), pr_item(), 0, 2)
    assert out.result == "needs_human"
    assert AddLabels(3, ("needs:human",)) in out.ops
    assert any(status in op.body for op in out.ops if isinstance(op, PostComment))


def test_review_approved_goes_to_qa():
    out = outcome_for(task("review", "pr", 7, "claude"), "finished", "Todo bien.\nVEREDICTO: APROBADO", frozenset(), None, 0, 2)
    assert (out.result, out.ops[-1]) == ("aprobado", AddLabels(7, ("agent:qa",)))


def test_review_changes_requests_fix_and_counts_round():
    out = outcome_for(task("review", "pr", 7, "claude"), "finished", "VEREDICTO: CAMBIOS", frozenset(), None, 1, 2)
    assert (out.result, out.review_rounds, out.ops[-1]) == ("cambios", 2, AddLabels(7, ("agent:fix",)))


def test_review_changes_after_max_rounds_escalates():
    out = outcome_for(task("review", "pr", 7, "claude"), "finished", "VEREDICTO: CAMBIOS", frozenset(), None, 2, 2)
    assert (out.result, out.review_rounds) == ("max_rondas", 3)
    assert AddLabels(7, ("needs:human",)) in out.ops


def test_review_without_verdict_escalates():
    out = outcome_for(task("review", "pr", 7, "claude"), "finished", "Revisé el código.", frozenset(), None, 0, 2)
    assert out.result == "sin_resultado"
    assert AddLabels(7, ("needs:human",)) in out.ops


@pytest.mark.parametrize(
    "text,expected",
    [
        ("VEREDICTO: APROBADO", "APROBADO"),
        ("**VEREDICTO: CAMBIOS**", "CAMBIOS"),
        ("VEREDICTO: **cambios**", "CAMBIOS"),
        ("Primero VEREDICTO: CAMBIOS\n...\nVEREDICTO: APROBADO", "APROBADO"),
        ("sin veredicto", None),
    ],
)
def test_parse_verdict(text, expected):
    assert parse_verdict(text) == expected


def test_fix_from_label_goes_back_to_review():
    out = outcome_for(task("fix", "pr", 7), "finished", "", frozenset(), None, 1, 2)
    assert (out.result, out.ops[-1]) == ("fix_aplicado", AddLabels(7, ("agent:review",)))


def test_fix_from_comment_asks_eduardo_again():
    out = outcome_for(task("fix", "pr", 7, trigger="comment"), "finished", "", frozenset(), None, 1, 2)
    assert out.ops[-1] == RequestReview(7)


def test_fix_that_asked_for_help_stops():
    out = outcome_for(task("fix", "pr", 7), "finished", "", frozenset({"needs:human"}), None, 1, 2)
    assert (out.result, out.ops) == ("needs_human", (RemoveLabel(7, "agent:working"), RemoveLabel(7, "agent:fix")))


def test_find_pr_by_branch_or_closes_and_not_by_similar_number():
    items = [
        pr_item(10, head="agent/30-otra"),
        pr_item(11, head="feature/x", body="Closes #3"),
        Item("qr", 3, "issue", "I", "", frozenset()),
    ]
    assert find_pr_for_issue(items, "qr", 3).number == 11
    assert find_pr_for_issue(items, "qr", 30).number == 10
    assert find_pr_for_issue(items, "otro", 3) is None


@pytest.mark.parametrize("status", ["finished", "error"])
@pytest.mark.parametrize(
    "role,kind,trigger_label",
    [("dev", "issue", "agent:dev"), ("review", "pr", "agent:review"), ("fix", "pr", "agent:fix")],
)
def test_trigger_label_is_always_removed(role, kind, trigger_label, status):
    out = outcome_for(task(role, kind, 7), status, "VEREDICTO: APROBADO", frozenset(), None, 0, 2)
    assert RemoveLabel(7, trigger_label) in out.ops



def test_fix_from_conflict_goes_back_to_agent_review():
    out = outcome_for(task("fix", "pr", 11, trigger="conflict"), "finished", "", frozenset(), None, 0, 2)
    assert (out.result, out.ops[-1]) == ("fix_aplicado", AddLabels(11, ("agent:review",)))


@pytest.mark.parametrize(
    "text,expected",
    [("QA: OK", "OK"), ("**QA: FALLA**", "FALLA"), ("QA: n/a", "N/A"), ("QA: FALLA\n...\nQA: OK", "OK"), ("VEREDICTO: APROBADO", None)],
)
def test_parse_qa_verdict(text, expected):
    assert parse_qa_verdict(text) == expected


@pytest.mark.parametrize("verdict,result", [("OK", "qa_ok"), ("N/A", "qa_na")])
def test_qa_ok_or_na_requests_human_review(verdict, result):
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", f"Probé todo.\nQA: {verdict}", frozenset(), None, 0, 2)
    assert (out.result, out.ops[-1]) == (result, RequestReview(7))
    assert RemoveLabel(7, "agent:qa") in out.ops


def test_qa_failure_sends_to_fix_and_counts_qa_round():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "QA: FALLA", frozenset(), None, 1, 2, qa_rounds=0)
    assert (out.result, out.review_rounds, out.qa_rounds, out.ops[-1]) == ("qa_falla", 1, 1, AddLabels(7, ("agent:fix",)))


def test_qa_failure_after_max_rounds_escalates():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "QA: FALLA", frozenset(), None, 0, 2, qa_rounds=2)
    assert (out.result, out.qa_rounds) == ("max_rondas_qa", 3)
    assert AddLabels(7, ("needs:human",)) in out.ops


def test_qa_without_qa_verdict_escalates():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "VEREDICTO: APROBADO", frozenset(), None, 0, 2)
    assert out.result == "sin_resultado" and AddLabels(7, ("needs:human",)) in out.ops


def test_docs_with_pr_goes_to_review_like_dev():
    out = outcome_for(task("docs", "issue", 3, "claude"), "finished", "", frozenset(), pr_item(), 0, 2)
    assert out.result == "pr_abierto"
    assert out.ops == (
        RemoveLabel(3, "agent:working"),
        RemoveLabel(3, "agent:docs"),
        AddLabels(7, ("agent:review", "engine:claude")),
    )


def test_review_rounds_and_qa_rounds_are_preserved_when_unchanged():
    out = outcome_for(task("fix", "pr", 7), "finished", "", frozenset(), None, 1, 2, qa_rounds=1)
    assert (out.review_rounds, out.qa_rounds) == (1, 1)
