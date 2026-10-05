"""Qué hacer en GitHub cuando termina una conversación. Función pura."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import (
    LABEL_DEV,
    LABEL_DOCS,
    LABEL_FIX,
    LABEL_HUMAN,
    LABEL_QA,
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
QA_VERDICT_RE = re.compile(r"QA:\s*\**\s*(OK|FALLA|N/A)", re.IGNORECASE)
SNIPPET_CHARS = 1500
NORMAL_STATUSES = frozenset({"finished", "idle"})
TRIGGER_LABELS = {"dev": LABEL_DEV, "review": LABEL_REVIEW, "fix": LABEL_FIX, "qa": LABEL_QA, "docs": LABEL_DOCS}


@dataclass(frozen=True)
class Outcome:
    result: str
    ops: tuple[GitHubOp, ...]
    review_rounds: int
    qa_rounds: int = 0


def parse_verdict(text: str) -> str | None:
    matches = VERDICT_RE.findall(text or "")
    return matches[-1].upper() if matches else None


def parse_qa_verdict(text: str) -> str | None:
    matches = QA_VERDICT_RE.findall(text or "")
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
    qa_rounds: int = 0,
) -> Outcome:
    n = task.number
    # El label disparador se quita siempre: si quedara, la tarea se repetiría en bucle.
    ops: list[GitHubOp] = [RemoveLabel(n, LABEL_WORKING), RemoveLabel(n, TRIGGER_LABELS[task.role])]

    def done(result: str, review: int = rounds, qa: int = qa_rounds) -> Outcome:
        return Outcome(result, tuple(ops), review, qa)

    def escalate(result: str, message: str, review: int = rounds, qa: int = qa_rounds) -> Outcome:
        ops.extend([AddLabels(n, (LABEL_HUMAN,)), PostComment(n, message)])
        return done(result, review, qa)

    if status not in NORMAL_STATUSES:
        return escalate(
            "needs_human",
            f"⚠️ La tarea `{task.role}` con `{task.engine}` terminó con estado `{status}`. "
            f"Revisa la conversación `{task.conversation_id}` en Canvas.\n\n"
            f"Última respuesta del agente:\n\n{_quote(final_response)}",
        )

    if task.role in ("dev", "docs"):
        if pr is not None:
            ops.append(AddLabels(pr.number, (LABEL_REVIEW, f"engine:{task.engine}")))
            return done("pr_abierto")
        if LABEL_HUMAN in current_labels:
            return done("needs_human")
        return escalate(
            "sin_resultado",
            "El agente terminó sin abrir un PR ni pedir ayuda.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    if task.role == "review":
        verdict = parse_verdict(final_response)
        if verdict == "APROBADO":
            ops.append(AddLabels(n, (LABEL_QA,)))
            return done("aprobado")
        if verdict == "CAMBIOS":
            new_rounds = rounds + 1
            if new_rounds <= max_rounds:
                ops.append(AddLabels(n, (LABEL_FIX,)))
                return done("cambios", review=new_rounds)
            return escalate(
                "max_rondas",
                f"El reviewer volvió a pedir cambios y ya se hicieron {max_rounds} rondas "
                "automáticas. Necesito tu decisión: comenta con @openhands lo que debe hacer "
                "el dev, o mergea/cierra el PR.",
                review=new_rounds,
            )
        return escalate(
            "sin_resultado",
            "El reviewer terminó sin dejar `VEREDICTO: APROBADO` ni `VEREDICTO: CAMBIOS`.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    if task.role == "qa":
        verdict = parse_qa_verdict(final_response)
        if verdict in ("OK", "N/A"):
            ops.append(RequestReview(n))
            return done("qa_ok" if verdict == "OK" else "qa_na")
        if verdict == "FALLA":
            new_qa = qa_rounds + 1
            if new_qa <= max_rounds:
                ops.append(AddLabels(n, (LABEL_FIX,)))
                return done("qa_falla", qa=new_qa)
            return escalate(
                "max_rondas_qa",
                f"QA volvió a fallar y ya se hicieron {max_rounds} rondas automáticas de QA. "
                "Revisa las capturas del último comentario de QA y decide cómo seguir.",
                qa=new_qa,
            )
        return escalate(
            "sin_resultado",
            "QA terminó sin dejar `QA: OK`, `QA: FALLA` ni `QA: N/A`.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    # role == "fix"
    if LABEL_HUMAN in current_labels:
        return done("needs_human")
    # Tras una corrección por label o por conflicto vuelve a revisar el agente: una resolución de
    # conflictos puede descartar funcionalidad sin que el CI lo note. Si lo pidió Eduardo, le vuelve a él.
    ops.append(RequestReview(n) if task.trigger == "comment" else AddLabels(n, (LABEL_REVIEW,)))
    return done("fix_aplicado")
