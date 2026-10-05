"""Ciclo del dispatcher: lee Canvas y GitHub, decide y ejecuta."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from collections.abc import Callable

from .board import AddToBoard, plan_board
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
    BlockedNotice,
    DocsOnlyNotice,
    EscalateConflict,
    FinishTask,
    GitHubOp,
    Item,
    PauseConversation,
    PostComment,
    ReleaseOrphan,
    RemoveLabel,
    RequestReview,
    StartTask,
)
from .outcomes import find_pr_for_issue, outcome_for
from .prompts import build_prompt
from .state import State, StateStore
from .workspace import WorkspaceError, redact

log = logging.getLogger("dispatcher")


class Dispatcher:
    def __init__(self, cfg: Config, github, canvas, workspace, store: StateStore, metrics: MetricsLog,
                 clock: Callable[[], float] = time.time, board=None):
        self.cfg = cfg
        self.github = github
        self.canvas = canvas
        self.workspace = workspace
        self.store = store
        self.metrics = metrics
        self.clock = clock
        self.board = board

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
            repo_items = self.github.list_open_items(repo)
            items += repo_items
            comments += self.github.list_comments_since(repo, state.comments_since)
            # Un @openhands también puede venir en una review del PR ("Review changes" → Comment).
            prs = [i.number for i in repo_items if i.kind == "pr"]
            comments += self.github.list_pr_reviews_since(repo, prs, state.comments_since)
        items = [self._with_merge_state(i) for i in items]
        for item in items:
            # El contador de intentos por conflictos se reinicia cuando el PR queda limpio.
            if item.kind == "pr" and item.mergeable_state not in (None, "dirty", "unknown"):
                state.conflict_attempts.pop(item.key, None)

        actions = decide(items, comments, convs, state, self.cfg, now)
        for action in actions:
            try:
                self._apply(action, state, items, now)
            except Exception:
                log.exception("Falló la acción %s", type(action).__name__)
            self.store.save(state)
        if self.board is not None:
            try:
                self._sync_board(items)
            except Exception:
                log.exception("Falló la sincronización del tablero")
        return actions

    def _sync_board(self, items: list[Item]) -> None:
        # Usa los labels del inicio del ciclo: los cambios de este ciclo se reflejan en el siguiente.
        for op in plan_board(items, self.board.load(), self.cfg.repos):
            try:
                if isinstance(op, AddToBoard):
                    if not op.item.node_id:
                        continue
                    self.board.set_column(self.board.add(op.item.node_id), op.column)
                else:
                    self.board.set_column(op.board_item_id, op.column)
            except Exception as exc:
                log.warning("No pude actualizar el tablero para %s: %s", getattr(op, "key", None) or op.item.key, exc)

    def _with_merge_state(self, item: Item) -> Item:
        if item.kind != "pr":
            return item
        try:
            return replace(item, mergeable_state=self.github.get_merge_state(item.repo, item.number))
        except Exception:
            log.warning("No pude leer el estado de merge de %s", item.key)
            return item

    def _apply(self, action: Action, state: State, items: list[Item], now: float) -> None:
        if isinstance(action, PauseConversation):
            self.canvas.pause(action.conversation_id)
        elif isinstance(action, StartTask):
            self._start(action, state, now)
        elif isinstance(action, FinishTask):
            self._finish(action, state, items, now)
        elif isinstance(action, ReleaseOrphan):
            self._release_orphan(action.item)
        elif isinstance(action, EscalateConflict):
            item = action.item
            self.github.add_labels(item.repo, item.number, [LABEL_HUMAN])
            self.github.comment(
                item.repo, item.number,
                "⚠️ El PR sigue con conflictos después de los intentos automáticos de resolución. "
                "Revísalo, o comenta con @openhands cómo resolverlos.",
            )
        elif isinstance(action, DocsOnlyNotice):
            item = action.item
            self.github.comment(
                item.repo, item.number,
                "ℹ️ Este repo es de **solo documentación**: los agentes no cambian código acá, así que "
                "`agent:dev` no arranca. Si es una tarea de documentación, usá `agent:docs`.",
            )
            state.docs_only_notified.add(item.key)
        elif isinstance(action, BlockedNotice):
            item = action.item
            deps = ", ".join(f"#{d}" for d in action.deps)
            self.github.comment(
                item.repo, item.number,
                f"⏸️ Este issue depende de {deps}, que sigue abierto. Arranca solo cuando se cierre. "
                "Para empezar igual, comenta con @openhands.",
            )
            state.blocked_notified[item.key] = list(action.deps)

    def _release_orphan(self, item: Item) -> None:
        self.github.remove_label(item.repo, item.number, LABEL_WORKING)
        self.github.add_labels(item.repo, item.number, [LABEL_HUMAN])
        self.github.comment(
            item.repo, item.number,
            "⚠️ Este item tenía `agent:working` pero el dispatcher no tiene una tarea activa para él "
            "(posible reinicio o estado perdido). Revisa Canvas por si quedó una conversación "
            "huérfana y vuelve a poner el label disparador o comenta con @openhands.",
        )

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
        if a.trigger == "conflict":
            state.conflict_attempts[item.key] = state.conflict_attempts.get(item.key, 0) + 1
        state.blocked_notified.pop(item.key, None)
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
        # La respuesta del agente puede terminar en un comentario público: nunca con el token.
        final = redact(final, (self.cfg.github_token,))
        try:
            labels = self.github.get_labels(task.repo, task.number)
        except Exception:
            log.warning("No pude leer los labels de %s", task.key)
            labels = frozenset()
        pr = find_pr_for_issue(items, task.repo, task.number) if task.kind == "issue" else None
        outcome = outcome_for(
            task, a.status, final, labels, pr,
            state.review_rounds.get(task.key, 0), self.cfg.max_review_rounds,
            qa_rounds=state.qa_rounds.get(task.key, 0),
        )
        failed = []
        for op in outcome.ops:
            try:
                self._apply_op(task.repo, op)
            except Exception as exc:
                log.warning("Falló %s en %s: %s", type(op).__name__, task.key, exc)
                failed.append(type(op).__name__)
        if failed:
            try:
                self.github.add_labels(task.repo, task.number, [LABEL_HUMAN])
                self.github.comment(
                    task.repo, task.number,
                    f"⚠️ La tarea `{task.role}` terminó (`{outcome.result}`), pero fallaron estas "
                    f"operaciones en GitHub: {', '.join(failed)}. Revisa el estado a mano.",
                )
            except Exception:
                log.exception("Tampoco pude escalar %s", task.key)
        # Siempre se libera la tarea: si no, su motor queda bloqueado para siempre.
        state.review_rounds[task.key] = outcome.review_rounds
        state.qa_rounds[task.key] = outcome.qa_rounds
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
