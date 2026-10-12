"""Tipos compartidos del dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

Kind = Literal["issue", "pr"]
Role = Literal["dev", "review", "fix", "qa", "docs"]
Trigger = Literal["label", "comment", "conflict"]

MENTION = "@openhands"
LABEL_DEV = "agent:dev"
LABEL_WORKING = "agent:working"
LABEL_REVIEW = "agent:review"
LABEL_FIX = "agent:fix"
LABEL_HUMAN = "needs:human"
LABEL_QA = "agent:qa"
LABEL_DOCS = "agent:docs"


def item_key(repo: str, number: int) -> str:
    return f"{repo}#{number}"


@dataclass(frozen=True)
class Slot:
    """Un puesto: una cuenta de un motor, con un nivel."""

    name: str
    engine: str
    tier: str


def engine_from_labels(labels: frozenset[str], default: str | None) -> str | None:
    # Orden fijo: si un PR quedó con dos engine:* (pasó en nikito#22), gana siempre el mismo.
    for engine in ("claude", "codex", "gemini"):
        if f"engine:{engine}" in labels:
            return engine
    return default


@dataclass(frozen=True)
class Item:
    """Un issue o PR abierto, tal como lo devuelve GitHub."""

    repo: str
    number: int
    kind: Kind
    title: str
    body: str
    labels: frozenset[str]
    head_ref: str | None = None  # rama del PR
    node_id: str = ""  # id GraphQL, para el tablero de Projects
    mergeable_state: str | None = None  # solo PRs: "dirty" = conflictos con la base
    draft: bool = False  # solo PRs: en borrador no pasan a review ni a QA

    @property
    def key(self) -> str:
        return item_key(self.repo, self.number)


@dataclass(frozen=True)
class Comment:
    id: int
    repo: str
    number: int
    author: str
    body: str


@dataclass(frozen=True)
class ConvInfo:
    """Estado y consumo de una conversación de Canvas."""

    id: str
    status: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class ActiveTask:
    repo: str
    number: int
    kind: Kind
    role: Role
    engine: str
    trigger: Trigger
    conversation_id: str
    started_at: float
    workspace: str
    slot: str = ""
    comment_id: int | None = None

    @property
    def key(self) -> str:
        return item_key(self.repo, self.number)


# Acciones que decide() pide ejecutar.
@dataclass(frozen=True)
class StartTask:
    item: Item
    role: Role
    engine: str
    trigger: Trigger
    instruction: str = ""
    comment_id: int | None = None
    slot: str = ""


@dataclass(frozen=True)
class FinishTask:
    task: ActiveTask
    status: str  # finished | idle | error | stuck | missing | timeout
    conv: ConvInfo | None


@dataclass(frozen=True)
class PauseConversation:
    conversation_id: str


@dataclass(frozen=True)
class ReleaseOrphan:
    """Un item tiene agent:working pero no hay una tarea activa que lo respalde."""

    item: Item


@dataclass(frozen=True)
class EscalateConflict:
    """El PR sigue con conflictos después de los intentos automáticos."""

    item: Item


@dataclass(frozen=True)
class BlockedNotice:
    """El issue tiene agent:dev pero depende de issues todavía abiertos."""

    item: Item
    deps: tuple[int, ...]


@dataclass(frozen=True)
class DocsOnlyNotice:
    """agent:dev en un repo de solo documentación: no arranca y se avisa una vez."""

    item: Item


@dataclass(frozen=True)
class UnassignableNotice:
    """Ningún puesto configurado puede tomar la tarea (motor forzado sin puesto o PR sin reviewer posible)."""

    item: Item
    role: Role
    comment_id: int | None = None


Action = Union[
    StartTask, FinishTask, PauseConversation, ReleaseOrphan, EscalateConflict, BlockedNotice, DocsOnlyNotice,
    UnassignableNotice,
]


# Operaciones sobre GitHub que outcome_for() pide ejecutar (siempre en el repo de la tarea).
@dataclass(frozen=True)
class AddLabels:
    number: int
    labels: tuple[str, ...]


@dataclass(frozen=True)
class RemoveLabel:
    number: int
    label: str


@dataclass(frozen=True)
class PostComment:
    number: int
    body: str


@dataclass(frozen=True)
class RequestReview:
    number: int


GitHubOp = Union[AddLabels, RemoveLabel, PostComment, RequestReview]
