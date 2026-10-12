"""Qué motor y qué puesto toma cada tarea (spec fase 5a, sección 4). Funciones puras."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Slot, engine_from_labels

LABEL_ARCH = "kind:architecture"
LABEL_IMAGES = "needs:images"
LONG_EXHAUSTION_S = 7200  # un dev deja de esperar a su puesto si falta más que esto para el reinicio
ALL_ENGINES = ("claude", "codex", "gemini")


def task_size(labels: frozenset[str]) -> str:
    for size in ("S", "L"):
        if f"size:{size}" in labels:
            return size
    return "M"


def _dev_engines(labels: frozenset[str]) -> set[str]:
    return {e for e in ALL_ENGINES if f"engine:{e}" in labels}


def preferences(role: str, labels: frozenset[str], kind: str) -> tuple[tuple[str, ...], bool]:
    """Motores en orden de preferencia y si la tarea espera al primero en vez de usar el respaldo."""
    if kind == "issue":
        forced = engine_from_labels(labels, None)
        if forced is not None:
            return (forced,), True
        if role == "docs":
            return ("codex", "gemini", "claude"), False
        if LABEL_ARCH in labels or task_size(labels) == "L":
            return ("claude", "codex"), True
        if LABEL_IMAGES in labels:
            return ("codex", "gemini"), True
        return ("codex", "gemini", "claude"), True
    # PR: los engine:* dicen quién programó.
    dev = engine_from_labels(labels, None)
    if role == "review":
        # Por ahora revisan Claude y Codex (spec, fuera de alcance: Gemini como reviewer).
        order = ("codex",) if dev == "claude" else ("claude", "codex")
        excluded = _dev_engines(labels) or {"codex"}
        return tuple(e for e in order if e not in excluded), False
    if role == "qa":
        return ("gemini", "codex", "claude"), False
    base = dev or "codex"
    return (base, *[e for e in ("codex", "claude", "gemini") if e != base]), False


def choose_slot(
    prefs: Iterable[str], waits: bool, slots: Iterable[Slot], busy: set[str],
    exhausted: Mapping[str, float], now: float,
) -> Slot | None:
    slots = list(slots)
    for i, engine in enumerate(prefs):
        own = [s for s in slots if s.engine == engine]
        if not own:
            continue
        available = [s for s in own if exhausted.get(s.name, 0.0) <= now]
        free = [s for s in available if s.name not in busy]
        if free:
            return free[0]
        if i == 0 and waits:
            if available:
                return None  # ocupado: el dev espera a su puesto
            soonest = min(exhausted[s.name] for s in own)
            if soonest - now < LONG_EXHAUSTION_S:
                return None  # agotado por poco: espera el reinicio
    return None
