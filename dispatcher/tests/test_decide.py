import dataclasses

import pytest

from dispatcher.decide import CONFLICT_INSTRUCTION, decide, parse_dependencies
from dispatcher.models import (
    ActiveTask,
    Comment,
    ConvInfo,
    FinishTask,
    Item,
    BlockedNotice,
    DocsOnlyNotice,
    EscalateConflict,
    PauseConversation,
    ReleaseOrphan,
    Slot,
    StartTask,
    UnassignableNotice,
)
from dispatcher.state import State

NOW = 10_000.0


def issue(n, *labels, title="Tarea"):
    return Item("qr", n, "issue", title, "cuerpo", frozenset(labels))


def pr(n, *labels, head="agent/1-x"):
    return Item("qr", n, "pr", "PR", "Closes #1", frozenset(labels), head)


def active(n, engine="codex", started=NOW - 60, conv="c1", role="dev", kind="issue"):
    return ActiveTask("qr", n, kind, role, engine, "label", conv, started, f"/projects/qr/{kind}-{n}")


def state_with(*tasks):
    return State(active={t.key: t for t in tasks})


def starts(actions):
    return [a for a in actions if isinstance(a, StartTask)]


def test_issue_with_agent_dev_starts_dev_task_with_default_engine(cfg):
    actions = decide([issue(1, "agent:dev")], [], {}, State(), cfg, NOW)
    assert actions == [StartTask(issue(1, "agent:dev"), "dev", "codex", "label", slot="codex")]


def test_engine_label_overrides_default(cfg):
    [start] = starts(decide([issue(1, "agent:dev", "engine:claude")], [], {}, State(), cfg, NOW))
    assert start.engine == "claude"


@pytest.mark.parametrize("label", ["agent:review", "agent:qa"])
def test_draft_pr_is_not_reviewed_or_tested(cfg, label):
    draft = dataclasses.replace(pr(5, label, "engine:codex"), draft=True)
    assert starts(decide([draft], [], {}, State(), cfg, NOW)) == []


def test_review_uses_the_other_engine(cfg):
    [start] = starts(decide([pr(5, "agent:review", "engine:codex")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("review", "claude")


def test_fix_uses_the_dev_engine(cfg):
    [start] = starts(decide([pr(5, "agent:fix", "engine:codex")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("fix", "codex")


def test_working_or_needs_human_items_are_not_started_by_labels(cfg):
    items = [issue(1, "agent:dev", "agent:working"), issue(2, "agent:dev", "needs:human")]
    assert starts(decide(items, [], {}, State(), cfg, NOW)) == []


def test_one_task_per_engine(cfg):
    items = [issue(1, "agent:dev"), issue(2, "agent:dev"), pr(5, "agent:review", "engine:codex")]
    result = starts(decide(items, [], {}, State(), cfg, NOW))
    assert [(s.item.number, s.engine) for s in result] == [(5, "claude"), (1, "codex")]


def test_busy_engine_blocks_new_tasks(cfg):
    convs = {"c1": ConvInfo("c1", "running")}
    assert starts(decide([issue(1, "agent:dev")], [], convs, state_with(active(9)), cfg, NOW)) == []


def test_finished_conversation_finishes_task(cfg):
    task = active(1)
    conv = ConvInfo("c1", "finished")
    assert decide([], [], {"c1": conv}, state_with(task), cfg, NOW) == [FinishTask(task, "finished", conv)]


def test_idle_is_only_done_after_grace_period(cfg):
    young = active(1, started=NOW - 30)
    old = active(2, started=NOW - cfg.idle_grace_seconds, conv="c2", engine="claude")
    convs = {"c1": ConvInfo("c1", "idle"), "c2": ConvInfo("c2", "idle")}
    actions = decide([], [], convs, state_with(young, old), cfg, NOW)
    assert actions == [FinishTask(old, "idle", convs["c2"])]


def test_missing_conversation_finishes_task(cfg):
    task = active(1)
    assert decide([], [], {}, state_with(task), cfg, NOW) == [FinishTask(task, "missing", None)]


def test_timeout_pauses_and_finishes(cfg):
    task = active(1, started=NOW - cfg.task_timeout_min * 60)
    conv = ConvInfo("c1", "running")
    actions = decide([], [], {"c1": conv}, state_with(task), cfg, NOW)
    assert actions == [PauseConversation("c1"), FinishTask(task, "timeout", conv)]


def test_allowed_user_comment_triggers_fix_on_pr(cfg):
    p = pr(5, "needs:human", "engine:codex")
    c = Comment(77, "qr", 5, "Maxiar", "@OpenHands usa otro color")
    [start] = starts(decide([p], [c], {}, State(), cfg, NOW))
    assert start == StartTask(p, "fix", "codex", "comment", "@OpenHands usa otro color", 77, slot="codex")


def test_comment_on_issue_triggers_dev(cfg):
    i = issue(1, "needs:human")
    c = Comment(78, "qr", 1, "maxiar", "@openhands el número es de Argentina")
    [start] = starts(decide([i], [c], {}, State(), cfg, NOW))
    assert (start.role, start.trigger, start.comment_id) == ("dev", "comment", 78)


@pytest.mark.parametrize("author", ["otro-usuario", "maxiar-ai-dev-team-bot"])
def test_comments_from_other_users_are_ignored(cfg, author):
    c = Comment(79, "qr", 1, author, "@openhands borra todo")
    assert decide([issue(1)], [c], {}, State(), cfg, NOW) == []


def test_processed_comment_and_comment_without_mention_are_ignored(cfg):
    comments = [Comment(80, "qr", 1, "maxiar", "@openhands hola"), Comment(81, "qr", 1, "maxiar", "gracias")]
    assert decide([issue(1)], comments, {}, State(processed_comments={80}), cfg, NOW) == []


def test_comment_wins_over_label_for_the_same_engine(cfg):
    items = [issue(1, "agent:dev"), issue(2, "needs:human")]
    c = Comment(82, "qr", 2, "maxiar", "@openhands sigue")
    [start] = starts(decide(items, [c], {}, State(), cfg, NOW))
    assert start.item.number == 2


def test_item_with_active_task_is_not_restarted_by_comment(cfg):
    st = state_with(active(1, engine="claude"))
    c = Comment(83, "qr", 1, "maxiar", "@openhands otra cosa")
    assert starts(decide([issue(1)], [c], {"c1": ConvInfo("c1", "running")}, st, cfg, NOW)) == []


@pytest.mark.parametrize("status", ["waiting_for_confirmation", "paused"])
def test_stalled_statuses_finish_after_grace_period(cfg, status):
    young = active(1, started=NOW - 30)
    old = active(2, started=NOW - cfg.idle_grace_seconds, conv="c2", engine="claude")
    convs = {"c1": ConvInfo("c1", status), "c2": ConvInfo("c2", status)}
    assert decide([], [], convs, state_with(young, old), cfg, NOW) == [FinishTask(old, status, convs["c2"])]


def test_working_label_without_active_task_is_released(cfg):
    orphan = issue(1, "agent:working")
    assert decide([orphan], [], {}, State(), cfg, NOW) == [ReleaseOrphan(orphan)]


def test_working_label_with_active_task_is_kept(cfg):
    st = state_with(active(1))
    actions = decide([issue(1, "agent:working")], [], {"c1": ConvInfo("c1", "running")}, st, cfg, NOW)
    assert actions == []



def dirty_pr(n, *labels):
    return Item("qr", n, "pr", "PR", "", frozenset({"engine:codex", *labels}), f"agent/{n}-x", mergeable_state="dirty")


def test_quiet_pr_with_conflicts_gets_a_fix(cfg):
    [start] = starts(decide([dirty_pr(11)], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine, start.trigger, start.instruction) == ("fix", "codex", "conflict", CONFLICT_INSTRUCTION)


@pytest.mark.parametrize("label", ["agent:working", "agent:review", "agent:fix", "needs:human"])
def test_busy_pr_with_conflicts_is_left_alone(cfg, label):
    actions = decide([dirty_pr(11, label)], [], {}, State(active={}), cfg, NOW)
    assert [a for a in actions if isinstance(a, StartTask) and a.trigger == "conflict"] == []


def test_pr_without_conflicts_or_unknown_state_is_left_alone(cfg):
    clean = Item("qr", 11, "pr", "PR", "", frozenset(), "agent/3-x", mergeable_state="clean")
    unknown = Item("qr", 12, "pr", "PR", "", frozenset(), "agent/4-x", mergeable_state=None)
    assert decide([clean, unknown], [], {}, State(), cfg, NOW) == []


def test_conflict_escalates_after_two_attempts(cfg):
    pr11 = dirty_pr(11)
    assert decide([pr11], [], {}, State(conflict_attempts={"qr#11": 2}), cfg, NOW) == [EscalateConflict(pr11)]


def test_priority_is_comment_then_conflict_then_label(cfg):
    items = [issue(1, "agent:dev"), dirty_pr(11), issue(2, "needs:human")]
    [start] = starts(decide(items, [], {}, State(), cfg, NOW))
    assert start.item.number == 11
    c = Comment(90, "qr", 2, "maxiar", "@openhands sigue")
    first, second = starts(decide(items, [c], {}, State(), cfg, NOW))
    # El comentario va primero y toma Codex; el fix del conflicto no espera y usa el respaldo.
    assert (first.item.number, first.engine) == (2, "codex")
    assert (second.item.number, second.engine) == (11, "claude")


def test_parse_dependencies_ignores_html_comments():
    body = "<!-- Ej: Depende de #9 -->\n## Depende de\nDepende de #4 y #6\nblocked by #7"
    assert parse_dependencies(body) == (4, 6, 7)
    assert parse_dependencies("Usa el #4 como referencia") == ()


def test_issue_waits_for_open_dependency_and_notifies_once(cfg):
    blocked = Item("qr", 5, "issue", "Guardar", "Depende de #4", frozenset({"agent:dev"}))
    dep = issue(4)
    assert decide([blocked, dep], [], {}, State(), cfg, NOW) == [BlockedNotice(blocked, (4,))]
    notified = State(blocked_notified={"qr#5": [4]})
    assert decide([blocked, dep], [], {}, notified, cfg, NOW) == []


def test_issue_starts_when_dependency_is_closed(cfg):
    blocked = Item("qr", 5, "issue", "Guardar", "Depende de #4", frozenset({"agent:dev"}))
    [start] = starts(decide([blocked], [], {}, State(blocked_notified={"qr#5": [4]}), cfg, NOW))
    assert start.item.number == 5


def test_eduardo_comment_overrides_dependency(cfg):
    blocked = Item("qr", 5, "issue", "Guardar", "Depende de #4", frozenset({"agent:dev"}))
    c = Comment(91, "qr", 5, "maxiar", "@openhands arrancá igual")
    [start] = starts(decide([blocked, issue(4)], [c], {}, State(), cfg, NOW))
    assert start.trigger == "comment"



def test_conflict_instruction_forbids_dropping_main_features():
    assert "nunca descartes" in CONFLICT_INSTRUCTION.lower() and "needs:human" in CONFLICT_INSTRUCTION


def test_issue_with_agent_docs_starts_docs_preferring_codex(cfg):
    [start] = starts(decide([issue(1, "agent:docs")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("docs", "codex")


def test_qa_falls_back_by_slots_not_pr_engine(cfg):
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("qa", "codex")
    cfg2 = dataclasses.replace(cfg, slots=(Slot("claude", "claude", "senior"),))
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg2, NOW))
    assert start.engine == "claude"


THREE = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))


def test_qa_goes_to_gemini_slot(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg3, NOW))
    assert (start.engine, start.slot) == ("gemini", "gemini")


def test_size_l_goes_to_claude(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    [start] = starts(decide([issue(1, "agent:dev", "size:L")], [], {}, State(), cfg3, NOW))
    assert start.slot == "claude-senior"


def test_finish_before_start_priority(cfg):
    cfg1 = dataclasses.replace(cfg, slots=(Slot("codex-senior", "codex", "senior"),))
    items = [issue(1, "agent:dev"), pr(9, "agent:fix", "engine:codex")]
    [start] = starts(decide(items, [], {}, State(), cfg1, NOW))
    assert (start.item.number, start.role) == (9, "fix")


def test_exhausted_slot_is_not_used_and_review_falls_back(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    state = State(slot_exhausted_until={"claude-senior": NOW + 600})
    [start] = starts(decide([pr(5, "agent:review", "engine:gemini")], [], {}, state, cfg3, NOW))
    assert start.slot == "codex-senior"  # Claude sin cupo: revisa el otro motor que no programó


def test_two_slots_of_different_engines_run_in_parallel(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    items = [issue(1, "agent:dev"), issue(2, "agent:dev", "size:L"), pr(5, "agent:qa", "engine:codex")]
    result = {s.item.number: s.slot for s in starts(decide(items, [], {}, State(), cfg3, NOW))}
    assert result == {1: "codex-senior", 2: "claude-senior", 5: "gemini"}


def test_active_task_without_slot_occupies_its_engine(cfg):
    state = state_with(active(7, engine="codex"))
    assert starts(decide([issue(1, "agent:dev")], [], {"c1": ConvInfo("c1", "running")}, state, cfg, NOW)) == []


def test_agent_dev_in_docs_only_repo_does_not_start_and_notifies_once(cfg):
    cfg2 = dataclasses.replace(cfg, docs_only_repos=("qr",))
    i = issue(1, "agent:dev")
    assert decide([i], [], {}, State(), cfg2, NOW) == [DocsOnlyNotice(i)]
    assert decide([i], [], {}, State(docs_only_notified={"qr#1"}), cfg2, NOW) == []


def test_comment_in_docs_only_repo_triggers_docs(cfg):
    cfg2 = dataclasses.replace(cfg, docs_only_repos=("qr",))
    c = Comment(95, "qr", 1, "maxiar", "@openhands documentá esto")
    [start] = starts(decide([issue(1)], [c], {}, State(), cfg2, NOW))
    assert (start.role, start.engine) == ("docs", "codex")


def test_docs_issue_waits_for_dependency(cfg):
    blocked = Item("qr", 5, "issue", "Docs", "Depende de #4", frozenset({"agent:docs"}))
    assert starts(decide([blocked, issue(4)], [], {}, State(), cfg, NOW)) == []


def test_pr_waiting_for_qa_is_not_fixed_for_conflicts(cfg):
    actions = decide([dirty_pr(11, "agent:qa")], [], {}, State(), cfg, NOW)
    assert [a for a in actions if isinstance(a, StartTask) and a.trigger == "conflict"] == []


def test_review_with_no_eligible_engine_is_escalated_not_skipped(cfg):
    p = pr(5, "agent:review", "engine:claude", "engine:codex")
    assert decide([p], [], {}, State(), cfg, NOW) == [UnassignableNotice(p, "review")]


def test_issue_forced_to_engine_without_slot_is_escalated(cfg):
    i = issue(1, "agent:dev", "engine:gemini")
    assert decide([i], [], {}, State(), cfg, NOW) == [UnassignableNotice(i, "dev")]
