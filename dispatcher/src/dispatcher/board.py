"""Columna del tablero de GitHub Projects que corresponde a cada item. Funciones puras."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .models import LABEL_DEV, LABEL_HUMAN, LABEL_WORKING, Item
from .outcomes import find_pr_for_issue

BACKLOG = "Backlog"
READY = "Listo para agentes"
IN_PROGRESS = "En curso"
IN_REVIEW = "En review"
NEEDS_HUMAN = "Necesita a Eduardo"
# La automatización nativa del tablero también pone "Hecho" al cerrar o mergear, pero el
# dispatcher puede pisarla con datos del inicio del ciclo; por eso lo asegura él mismo.
DONE = "Hecho"


@dataclass(frozen=True)
class AddToBoard:
    item: Item
    column: str


@dataclass(frozen=True)
class SetColumn:
    board_item_id: str
    key: str
    column: str


def column_for(item: Item) -> str:
    if LABEL_HUMAN in item.labels:
        return NEEDS_HUMAN
    if LABEL_WORKING in item.labels:
        return IN_PROGRESS
    if item.kind == "pr":
        return IN_REVIEW
    if LABEL_DEV in item.labels:
        return READY
    return BACKLOG


def plan_board(
    items: Iterable[Item],
    current: Mapping[str, tuple[str, str | None]],
    repos: Iterable[str] | None = None,
) -> list[AddToBoard | SetColumn]:
    """repos: repos que atiende el dispatcher. Sus items del tablero que ya no están abiertos
    (cerrados o mergeados) pasan a Hecho. Los de otros repos no se tocan."""
    items = list(items)
    ops: list[AddToBoard | SetColumn] = []
    for item in sorted(items, key=lambda i: (i.repo, i.number)):
        column = column_for(item)
        if item.kind == "issue" and column in (BACKLOG, READY):
            # Un issue que ya tiene PR abierto avanza junto con su PR.
            pr = find_pr_for_issue(items, item.repo, item.number)
            if pr is not None:
                column = column_for(pr)
        entry = current.get(item.key)
        if entry is None:
            ops.append(AddToBoard(item, column))
        elif entry[1] != column:
            ops.append(SetColumn(entry[0], item.key, column))
    if repos is not None:
        watched = set(repos)
        open_keys = {i.key for i in items}
        for key, (board_id, column) in sorted(current.items()):
            if key.split("#", 1)[0] in watched and key not in open_keys and column != DONE:
                ops.append(SetColumn(board_id, key, DONE))
    return ops
