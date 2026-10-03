import pytest

from dispatcher.decide import decide
from dispatcher.models import (
    ActiveTask,
    Comment,
    ConvInfo,
    FinishTask,
    Item,
    PauseConversation,
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
    assert decide(items, [], {}, State(), cfg, NOW) == []


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
