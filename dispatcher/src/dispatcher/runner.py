"""Ciclo del dispatcher: lee Canvas y GitHub, decide y ejecuta."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .canvas import CanvasBusy
from .config import Config
from .decide import decide
from .metrics import MetricsLog, iso
from .models import (
    LABEL_DEV,
    LABEL_FIX,
    LABEL_HUMAN,
    LABEL_REVIEW,
    LABEL_WORKING,
    Action,
    ActiveTask,
    AddLabels,
    FinishTask,
    GitHubOp,
    Item,
    PauseConversation,
    PostComment,
    RemoveLabel,
    RequestReview,
    StartTask,
)
from .outcomes import find_pr_for_issue, outcome_for
from .prompts import build_prompt
from .state import State, StateStore
from .workspace import WorkspaceError

log = logging.getLogger("dispatcher")


class Dispatcher:
    def __init__(self, cfg: Config, github, canvas, workspace, store: StateStore, metrics: MetricsLog,
                 clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.github = github
        self.canvas = canvas
        self.workspace = workspace
        self.store = store
        self.metrics = metrics
        self.clock = clock

    def run_once(self) -> list[Action]:
        state = self.store.load()
        now = self.clock()
        if state.comments_since is None:
            # Solo cuentan los comentarios posteriores al primer arranque.
            state.comments_since = iso(now)
            self.store.save(state)

        # Primero Canvas y después GitHub: un PR abierto justo antes de que el agente
        # termine ya aparece en la lista de items de este ciclo.
        convs = self.canvas.get_conversations([t.conversation_id for t in state.active.values()])
        items: list[Item] = []
        comments = []
        for repo in self.cfg.repos:
            items += self.github.list_open_items(repo)
            comments += self.github.list_comments_since(repo, state.comments_since)

        actions = decide(items, comments, convs, state, self.cfg, now)
        for action in actions:
            try:
                self._apply(action, state, items, now)
            except Exception:
                log.exception("Falló la acción %s", type(action).__name__)
            self.store.save(state)
        return actions

    def _apply(self, action: Action, state: State, items: list[Item], now: float) -> None:
        if isinstance(action, PauseConversation):
            self.canvas.pause(action.conversation_id)
        elif isinstance(action, StartTask):
            self._start(action, state, now)
        elif isinstance(action, FinishTask):
            self._finish(action, state, items, now)

    def _start(self, a: StartTask, state: State, now: float) -> None:
        item = a.item
        branch = item.head_ref if item.kind == "pr" else None
        try:
            path = self.workspace.prepare(item.repo, item.kind, item.number, branch)
        except WorkspaceError as exc:
            self.github.add_labels(item.repo, item.number, [LABEL_HUMAN])
            self.github.comment(
                item.repo, item.number,
                f"⚠️ No pude preparar la copia del repo para la tarea `{a.role}`:\n\n```\n{exc}\n```",
            )
            if a.comment_id is not None:
                state.processed_comments.add(a.comment_id)
            return

        prompt = build_prompt(self.cfg.roles_dir, a.role, item, self.cfg.github_org, a.instruction)
        self.github.add_labels(item.repo, item.number, [LABEL_WORKING])
        try:
            conv_id = self.canvas.create_conversation(a.engine, str(path), prompt)
        except CanvasBusy:
            log.warning("Canvas está lleno; %s queda para el próximo ciclo", item.key)
            self.github.remove_label(item.repo, item.number, LABEL_WORKING)
            return
        except Exception:
            self.github.remove_label(item.repo, item.number, LABEL_WORKING)
            raise

        state.active[item.key] = ActiveTask(
            repo=item.repo, number=item.number, kind=item.kind, role=a.role, engine=a.engine,
            trigger=a.trigger, conversation_id=conv_id, started_at=now, workspace=str(path),
        )
        if a.comment_id is not None:
            state.processed_comments.add(a.comment_id)
        self.store.save(state)
        for label in (LABEL_DEV, LABEL_REVIEW, LABEL_FIX, LABEL_HUMAN):
            if label in item.labels:
                self.github.remove_label(item.repo, item.number, label)
        log.info("Inició %s %s con %s (conversación %s)", a.role, item.key, a.engine, conv_id)

    def _finish(self, a: FinishTask, state: State, items: list[Item], now: float) -> None:
        task = a.task
        final = ""
        if a.conv is not None:
            try:
                final = self.canvas.final_response(task.conversation_id)
            except Exception:
                log.warning("No pude leer la respuesta final de %s", task.conversation_id)
        labels = self.github.get_labels(task.repo, task.number)
        pr = find_pr_for_issue(items, task.repo, task.number) if task.kind == "issue" else None
        outcome = outcome_for(
            task, a.status, final, labels, pr,
            state.review_rounds.get(task.key, 0), self.cfg.max_review_rounds,
        )
        for op in outcome.ops:
            self._apply_op(task.repo, op)
        state.review_rounds[task.key] = outcome.review_rounds
        self.metrics.append(task, a.status, outcome.result, a.conv, now)
        state.active.pop(task.key, None)
        log.info("Terminó %s %s: %s (%s)", task.role, task.key, outcome.result, a.status)

    def _apply_op(self, repo: str, op: GitHubOp) -> None:
        if isinstance(op, AddLabels):
            self.github.add_labels(repo, op.number, list(op.labels))
        elif isinstance(op, RemoveLabel):
            self.github.remove_label(repo, op.number, op.label)
        elif isinstance(op, PostComment):
            self.github.comment(repo, op.number, op.body)
        elif isinstance(op, RequestReview):
            self.github.request_review(repo, op.number, list(self.cfg.allowed_users))


def run_forever(dispatcher: Dispatcher, poll_seconds: int, sleep: Callable[[float], None] = time.sleep) -> None:
    while True:
        try:
            dispatcher.run_once()
        except Exception:
            log.exception("Ciclo fallido; reintento en %s s", poll_seconds)
        sleep(poll_seconds)
