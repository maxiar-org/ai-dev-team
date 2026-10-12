"""Consumo por puesto y reglas de decisión del presupuesto (spec fase 5a, secciones 6 y 7). Funciones puras."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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


HOUR = 3600.0


def clean_metrics(rows: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    """Las filas que se pueden leer: el dispatcher puede estar escribiendo una, y las viejas no tienen todas las columnas."""
    out = []
    for r in rows:
        try:
            _ts(r["inicio"])
            float(r.get("duracion_min") or 0)
            r["repo"], r["numero"], r["rol"]
        except (KeyError, TypeError, ValueError):
            continue
        out.append(r)
    return out


def clean_limits(rows: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    out = []
    for r in rows:
        try:
            _ts(r["detectado"]), _ts(r["hasta"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(r)
    return out


def rework_per_issue(rows: Iterable[Mapping[str, str]]) -> float:
    return _rework(list(rows))


def _span(r: Mapping[str, str]) -> tuple[float, float]:
    start = _ts(r["inicio"])
    end = _ts(r["fin"]) if r.get("fin") else start + float(r.get("duracion_min") or 0) * 60
    return start, end


def hour_strip(metrics_rows, limit_rows, slot: str, now: float, active_since: float | None = None,
               exhausted_until: float | None = None) -> list[str]:
    work = [_span(r) for r in metrics_rows if r.get("puesto") == slot]
    if active_since is not None:
        work.append((active_since, now))
    out_of_quota = [(_ts(r["detectado"]), _ts(r["hasta"])) for r in limit_rows if r.get("puesto") == slot]
    if exhausted_until is not None and exhausted_until > now:
        out_of_quota.append((now - HOUR, exhausted_until))  # el corte actual, aunque falte su fila en limits.csv
    cells = []
    for i in range(24):
        a = now - DAY + i * HOUR
        b = a + HOUR
        if any(x < b and y > a for x, y in work):
            cells.append("trabajando")
        elif any(x < b and y > a for x, y in out_of_quota):
            cells.append("sin_cupo")
        else:
            cells.append("libre")
    return cells


def daily_hours(metrics_rows, slot_names: list[str], now: float, days: int, tz: ZoneInfo) -> list[dict]:
    today = datetime.fromtimestamp(now, tz).date()
    dates: list[date] = [today - timedelta(days=days - 1 - i) for i in range(days)]
    acc = {d: dict.fromkeys(slot_names, 0.0) for d in dates}
    for r in metrics_rows:
        slot = r.get("puesto")
        if slot not in slot_names:
            continue
        day = datetime.fromtimestamp(_ts(r["inicio"]), tz).date()
        if day in acc:
            acc[day][slot] += float(r.get("duracion_min") or 0)
    return [{"date": d, "minutes": acc[d]} for d in dates]


def _median(values: list[float]) -> float | None:
    values = sorted(values)
    n = len(values)
    if not n:
        return None
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def flow_times(merged: list[dict], metrics_rows, now: float, window_s: float) -> dict[str, float | None]:
    """Medianas en segundos: del primer dev al PR, del PR al merge y del primer dev al merge."""
    devs: dict[tuple[str, str], list] = defaultdict(list)
    for r in metrics_rows:
        if r.get("rol") == "dev" and r.get("tipo", "issue") == "issue":
            devs[(r.get("repo"), str(r.get("numero")))].append(r)
    to_pr, to_merge, total = [], [], []
    for p in merged:
        try:
            created, merged_at = _ts(p["created_at"]), _ts(p["merged_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if merged_at < now - window_s:
            continue
        to_merge.append(merged_at - created)
        rows = devs.get((p.get("repo"), str(p.get("closes")))) if p.get("closes") else None
        if not rows:
            continue
        first = min(_span(r)[0] for r in rows)
        opened = [_span(r)[1] for r in rows if r.get("resultado") == "pr_abierto"]
        if opened:
            to_pr.append(min(opened) - first)
        total.append(merged_at - first)
    return {"issue_to_pr": _median(to_pr), "pr_to_merge": _median(to_merge), "total": _median(total)}


UNASSIGNED = "sin asignar"


def project_costs(metrics_rows, slots: Iterable[Slot], costs: Mapping[str, float], image_usd: float,
                  now: float, window_s: float) -> dict[str, dict]:
    """Costo del rango por repo: el fijo de cada puesto se reparte según sus minutos en cada repo, más las imágenes."""
    slots = list(slots)
    names = {s.name for s in slots}
    rows = [r for r in metrics_rows if _ts(r["inicio"]) >= now - window_s and r.get("puesto") in names]
    out: dict[str, dict] = defaultdict(lambda: {"minutes": 0.0, "images": 0, "cost": 0.0})
    for slot in slots:
        mine = [r for r in rows if r.get("puesto") == slot.name]
        total = sum(float(r.get("duracion_min") or 0) for r in mine)
        fixed = costs.get(slot.name, 0.0) * (window_s / (30 * DAY))
        if total <= 0:
            if fixed:
                out[UNASSIGNED]["cost"] += fixed
            continue
        for r in mine:
            minutes = float(r.get("duracion_min") or 0)
            out[r["repo"]]["minutes"] += minutes
            out[r["repo"]]["cost"] += fixed * minutes / total
    for r in rows:
        images = int(r.get("imagenes_gemini") or 0)
        if images:
            out[r["repo"]]["images"] += images
            out[r["repo"]]["cost"] += images * image_usd
    return dict(out)
