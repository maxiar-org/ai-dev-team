import pytest

from dispatcher.decide import CONFLICT_INSTRUCTION, decide, parse_dependencies
from dispatcher.models import (
    ActiveTask,
    Comment,
    ConvInfo,
    FinishTask,
    Item,
    BlockedNotice,
    EscalateConflict,
    PauseConversation,
    ReleaseOrphan,
    StartTask,
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
    assert actions == [StartTask(issue(1, "agent:dev"), "dev", "codex", "label")]


def test_engine_label_overrides_default(cfg):
    [start] = starts(decide([issue(1, "agent:dev", "engine:claude")], [], {}, State(), cfg, NOW))
    assert start.engine == "claude"


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
    assert [(s.item.number, s.engine) for s in result] == [(1, "codex"), (5, "claude")]


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
    assert start == StartTask(p, "fix", "codex", "comment", "@OpenHands usa otro color", 77)


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
    [start] = starts(decide(items, [c], {}, State(), cfg, NOW))
    assert start.item.number == 2


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
