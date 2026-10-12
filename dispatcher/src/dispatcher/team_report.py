"""Consumo por puesto y reglas de decisión del presupuesto (spec fase 5a, secciones 6 y 7). Funciones puras."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from .models import Slot

DAY = 86400.0
REWORK_ROLES = ("fix", "qa")


@dataclass(frozen=True)
class SlotStats:
    tasks: int
    minutes: float
    utilization: float
    exhausted_hours: float
    limit_hits: int
    rework_per_issue: float
    cost_usd: float


def _ts(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def _exhausted_seconds(limit_rows: Iterable[Mapping[str, str]], slot: str, start: float, end: float) -> tuple[float, int]:
    total, hits = 0.0, 0
    for r in limit_rows:
        if r.get("puesto") != slot:
            continue
        a, b = _ts(r["detectado"]), _ts(r["hasta"])
        overlap = min(b, end) - max(a, start)
        if overlap > 0:
            total += overlap
        if start <= a < end:
            hits += 1
    return total, hits


def _rework(rows: list[Mapping[str, str]]) -> float:
    per_issue: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        per_issue[(r["repo"], r["numero"])] += r["rol"] in REWORK_ROLES
    return sum(per_issue.values()) / len(per_issue) if per_issue else 0.0


def slot_stats(metrics_rows, limit_rows, slots: Iterable[Slot], costs: Mapping[str, float],
               image_usd: float, now: float, window_s: float) -> dict[str, SlotStats]:
    start = now - window_s
    limit_rows = list(limit_rows)
    recent = [r for r in metrics_rows if r.get("inicio") and _ts(r["inicio"]) >= start]
    out: dict[str, SlotStats] = {}
    for slot in slots:
        rows = [r for r in recent if r.get("puesto") == slot.name]
        minutes = sum(float(r["duracion_min"] or 0) for r in rows)
        exhausted, hits = _exhausted_seconds(limit_rows, slot.name, start, now)
        images = sum(int(r.get("imagenes_gemini") or 0) for r in rows)
        cost = costs.get(slot.name, 0.0) * (window_s / (30 * DAY)) + images * image_usd
        out[slot.name] = SlotStats(len(rows), minutes, minutes * 60 / window_s, exhausted / 3600, hits, _rework(rows), cost)
    return out


def decision_alerts(limit_rows, metrics_rows, slots: Iterable[Slot], now: float) -> list[str]:
    alerts: list[str] = []
    limit_rows, metrics_rows = list(limit_rows), list(metrics_rows)
    for slot in slots:
        bad_days = sum(
            1 for d in range(5)
            if _exhausted_seconds(limit_rows, slot.name, now - (d + 1) * DAY, now - d * DAY)[0] > 2 * 3600
        )
        if bad_days >= 3:
            alerts.append(f"{slot.name}: sin cupo más de 2 h en {bad_days} de los últimos 5 días → subir de nivel o sumar un puesto")
        week = slot_stats(metrics_rows, limit_rows, [slot], {}, 0.0, now, 7 * DAY)[slot.name]
        if week.utilization < 0.20:
            alerts.append(f"{slot.name}: {week.utilization:.0%} de uso en 7 días → evaluar bajar de nivel")
    week_rows = [r for r in metrics_rows if r.get("inicio") and _ts(r["inicio"]) >= now - 7 * DAY]
    if _rework(week_rows) > 2:
        alerts.append(f"retrabajo alto: {_rework(week_rows):.1f} rondas de fix y QA por issue en 7 días → partir las tareas en issues más chicos")
    return alerts
