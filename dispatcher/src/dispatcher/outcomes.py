"""Qué hacer en GitHub cuando termina una conversación. Función pura."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import (
    LABEL_DEV,
    LABEL_FIX,
    LABEL_HUMAN,
    LABEL_REVIEW,
    LABEL_WORKING,
    ActiveTask,
    AddLabels,
    GitHubOp,
    Item,
    PostComment,
    RemoveLabel,
    RequestReview,
)

VERDICT_RE = re.compile(r"VEREDICTO:\s*\**\s*(APROBADO|CAMBIOS)", re.IGNORECASE)
SNIPPET_CHARS = 1500
NORMAL_STATUSES = frozenset({"finished", "idle"})
TRIGGER_LABELS = {"dev": LABEL_DEV, "review": LABEL_REVIEW, "fix": LABEL_FIX}


@dataclass(frozen=True)
class Outcome:
    result: str
    ops: tuple[GitHubOp, ...]
    review_rounds: int


def parse_verdict(text: str) -> str | None:
    matches = VERDICT_RE.findall(text or "")
    return matches[-1].upper() if matches else None


def find_pr_for_issue(items: Iterable[Item], repo: str, number: int) -> Item | None:
    prefix = f"agent/{number}-"
    closes = re.compile(rf"(?i)\b(?:closes|fixes|resolves|cierra)\s+#{number}\b")
    candidates = [
        i
        for i in items
        if i.repo == repo
        and i.kind == "pr"
        and ((i.head_ref or "").startswith(prefix) or closes.search(i.body or ""))
    ]
    return max(candidates, key=lambda i: i.number, default=None)


def _quote(text: str) -> str:
    snippet = (text or "").strip()
    if not snippet:
        return "> (el agente no dejó respuesta)"
    if len(snippet) > SNIPPET_CHARS:
        snippet = "…" + snippet[-SNIPPET_CHARS:]
    return "\n".join(f"> {line}" for line in snippet.splitlines())


def outcome_for(
    task: ActiveTask,
    status: str,
    final_response: str,
    current_labels: frozenset[str],
    pr: Item | None,
    rounds: int,
    max_rounds: int,
) -> Outcome:
    n = task.number
    # El label disparador se quita siempre: si quedara, la tarea se repetiría en bucle.
    ops: list[GitHubOp] = [RemoveLabel(n, LABEL_WORKING), RemoveLabel(n, TRIGGER_LABELS[task.role])]

    def escalate(result: str, message: str, new_rounds: int = rounds) -> Outcome:
        ops.extend([AddLabels(n, (LABEL_HUMAN,)), PostComment(n, message)])
        return Outcome(result, tuple(ops), new_rounds)

    if status not in NORMAL_STATUSES:
        return escalate(
            "needs_human",
            f"⚠️ La tarea `{task.role}` con `{task.engine}` terminó con estado `{status}`. "
            f"Revisa la conversación `{task.conversation_id}` en Canvas.\n\n"
            f"Última respuesta del agente:\n\n{_quote(final_response)}",
        )

    if task.role == "dev":
        if pr is not None:
            ops.append(AddLabels(pr.number, (LABEL_REVIEW, f"engine:{task.engine}")))
            return Outcome("pr_abierto", tuple(ops), rounds)
        if LABEL_HUMAN in current_labels:
            return Outcome("needs_human", tuple(ops), rounds)
        return escalate(
            "sin_resultado",
            "El agente terminó sin abrir un PR ni pedir ayuda.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    if task.role == "review":
        verdict = parse_verdict(final_response)
        if verdict == "APROBADO":
            ops.append(RequestReview(n))
            return Outcome("aprobado", tuple(ops), rounds)
        if verdict == "CAMBIOS":
            new_rounds = rounds + 1
            if new_rounds <= max_rounds:
                ops.append(AddLabels(n, (LABEL_FIX,)))
                return Outcome("cambios", tuple(ops), new_rounds)
            return escalate(
                "max_rondas",
                f"El reviewer volvió a pedir cambios y ya se hicieron {max_rounds} rondas "
                "automáticas. Necesito tu decisión: comenta con @openhands lo que debe hacer "
                "el dev, o mergea/cierra el PR.",
                new_rounds,
            )
        return escalate(
            "sin_resultado",
            "El reviewer terminó sin dejar `VEREDICTO: APROBADO` ni `VEREDICTO: CAMBIOS`.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    # role == "fix"
    if LABEL_HUMAN in current_labels:
        return Outcome("needs_human", tuple(ops), rounds)
    # Tras una corrección por label o por conflicto vuelve a revisar el agente: una resolución de
    # conflictos puede descartar funcionalidad sin que el CI lo note. Si lo pidió Eduardo, le vuelve a él.
    ops.append(RequestReview(n) if task.trigger == "comment" else AddLabels(n, (LABEL_REVIEW,)))
    return Outcome("fix_aplicado", tuple(ops), rounds)
