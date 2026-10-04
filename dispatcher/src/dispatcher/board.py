"""Columna del tablero de GitHub Projects que corresponde a cada item. Funciones puras."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .models import LABEL_DEV, LABEL_HUMAN, LABEL_WORKING, Item

BACKLOG = "Backlog"
READY = "Listo para agentes"
IN_PROGRESS = "En curso"
IN_REVIEW = "En review"
NEEDS_HUMAN = "Necesita a Eduardo"
# "Hecho" lo asigna la automatización nativa del tablero al cerrar o mergear.


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
    items: Iterable[Item], current: Mapping[str, tuple[str, str | None]]
) -> list[AddToBoard | SetColumn]:
    ops: list[AddToBoard | SetColumn] = []
    for item in sorted(items, key=lambda i: (i.repo, i.number)):
        column = column_for(item)
        entry = current.get(item.key)
        if entry is None:
            ops.append(AddToBoard(item, column))
        elif entry[1] != column:
            ops.append(SetColumn(entry[0], item.key, column))
    return ops
