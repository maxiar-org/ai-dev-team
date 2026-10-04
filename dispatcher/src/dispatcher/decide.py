"""Decide qué hacer en cada ciclo. Función pura: no hace I/O."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .config import Config
from .models import (
    LABEL_DEV,
    LABEL_FIX,
    LABEL_HUMAN,
    LABEL_REVIEW,
    LABEL_WORKING,
    MENTION,
    Action,
    BlockedNotice,
    Comment,
    ConvInfo,
    EscalateConflict,
    FinishTask,
    Item,
    PauseConversation,
    ReleaseOrphan,
    StartTask,
    engine_from_labels,
    item_key,
    other_engine,
)
from .state import State

DONE_STATUSES = frozenset({"finished", "error", "stuck"})
# Estados que solo cuentan como terminados después del período de gracia.
STALL_STATUSES = frozenset({"idle", "waiting_for_confirmation", "paused"})
MAX_CONFLICT_ATTEMPTS = 2
CONFLICT_INSTRUCTION = (
    "Este PR tiene conflictos con la rama base. Hacé `git fetch origin` y mergeá `origin/main` en "
    "esta rama, resolvé los conflictos preservando la funcionalidad de ambos lados, corré las "
    "verificaciones de AGENTS.md y pusheá. No cambies nada más."
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DEPENDS_LINE = re.compile(r"(?im)^.*\b(?:depende de|depends on|bloqueado por|blocked by)\b.*$")


def parse_dependencies(body: str) -> tuple[int, ...]:
    """Números de issue en líneas tipo "Depende de #4 y #6" (ignora comentarios HTML)."""
    text = _HTML_COMMENT.sub("", body or "")
    numbers: list[int] = []
    for line in _DEPENDS_LINE.findall(text):
        for n in re.findall(r"#(\d+)", line):
            if int(n) not in numbers:
                numbers.append(int(n))
    return tuple(numbers)


def decide(
    items: Iterable[Item],
    comments: Iterable[Comment],
    convs: Mapping[str, ConvInfo],
    state: State,
    cfg: Config,
    now: float,
) -> list[Action]:
    items = list(items)
    actions: list[Action] = []

    for task in state.active.values():
        conv = convs.get(task.conversation_id)
        elapsed = now - task.started_at
        if conv is None:
            actions.append(FinishTask(task, "missing", None))
        elif conv.status in DONE_STATUSES or (
            conv.status in STALL_STATUSES and elapsed >= cfg.idle_grace_seconds
        ):
            actions.append(FinishTask(task, conv.status, conv))
        elif elapsed >= cfg.task_timeout_min * 60:
            actions.append(PauseConversation(task.conversation_id))
            actions.append(FinishTask(task, "timeout", conv))

    # Las tareas que terminan en este ciclo liberan su motor recién en el siguiente.
    busy_engines = {t.engine for t in state.active.values()}
    busy_items = {t.key for t in state.active.values()}
    started_items: set[str] = set()
    for item in items:
        if LABEL_WORKING in item.labels and item.key not in busy_items:
            actions.append(ReleaseOrphan(item))
            started_items.add(item.key)
    open_issues = {(i.repo, i.number) for i in items if i.kind == "issue"}
    label_candidates = []
    for candidate in _label_candidates(items, cfg):
        deps = ()
        if candidate.role == "dev":
            deps = tuple(d for d in parse_dependencies(candidate.item.body) if (candidate.item.repo, d) in open_issues)
        if deps:
            if state.blocked_notified.get(candidate.item.key) != list(deps):
                actions.append(BlockedNotice(candidate.item, deps))
            continue
        label_candidates.append(candidate)
    conflict_candidates = []
    for item in items:
        if item.kind != "pr" or item.mergeable_state != "dirty":
            continue
        if item.labels & {LABEL_WORKING, LABEL_HUMAN, LABEL_REVIEW, LABEL_FIX} or item.key in busy_items:
            continue
        if state.conflict_attempts.get(item.key, 0) >= MAX_CONFLICT_ATTEMPTS:
            actions.append(EscalateConflict(item))
            started_items.add(item.key)
            continue
        engine = engine_from_labels(item.labels, cfg.default_dev_engine)
        conflict_candidates.append(StartTask(item, "fix", engine, "conflict", CONFLICT_INSTRUCTION))
    candidates = [*_comment_candidates(items, comments, state, cfg), *conflict_candidates, *label_candidates]
    for candidate in candidates:
        key = candidate.item.key
        if candidate.engine in busy_engines or key in busy_items or key in started_items:
            continue
        actions.append(candidate)
        busy_engines.add(candidate.engine)
        started_items.add(key)
    return actions


def _comment_candidates(
    items: list[Item], comments: Iterable[Comment], state: State, cfg: Config
) -> list[StartTask]:
    by_key = {item.key: item for item in items}
    out: list[StartTask] = []
    for comment in sorted(comments, key=lambda c: c.id):
        if comment.id in state.processed_comments:
            continue
        if comment.author.lower() not in cfg.allowed_users:
            continue
        if MENTION not in comment.body.lower():
            continue
        item = by_key.get(item_key(comment.repo, comment.number))
        if item is None:
            continue
        role = "fix" if item.kind == "pr" else "dev"
        engine = engine_from_labels(item.labels, cfg.default_dev_engine)
        out.append(StartTask(item, role, engine, "comment", comment.body, comment.id))
    return out


def _label_candidates(items: list[Item], cfg: Config) -> list[StartTask]:
    out: list[StartTask] = []
    for item in sorted(items, key=lambda i: (i.repo, i.number)):
        labels = item.labels
        if LABEL_WORKING in labels or LABEL_HUMAN in labels:
            continue
        dev_engine = engine_from_labels(labels, cfg.default_dev_engine)
        if item.kind == "issue" and LABEL_DEV in labels:
            out.append(StartTask(item, "dev", dev_engine, "label"))
        elif item.kind == "pr" and LABEL_FIX in labels:
            out.append(StartTask(item, "fix", dev_engine, "label"))
        elif item.kind == "pr" and LABEL_REVIEW in labels:
            out.append(StartTask(item, "review", other_engine(dev_engine), "label"))
    return out
