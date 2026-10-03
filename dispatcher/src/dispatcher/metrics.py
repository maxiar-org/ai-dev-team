"""Métricas del piloto: una fila por conversación terminada."""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from .models import ActiveTask, ConvInfo

FIELDS = [
    "repo", "numero", "tipo", "rol", "motor", "disparador", "inicio", "fin", "duracion_min",
    "estado_final", "resultado", "tokens_entrada", "tokens_salida", "tokens_cache",
    "costo_estimado_usd", "conversacion",
]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


class MetricsLog:
    def __init__(self, path: Path):
        self.path = path

    def append(self, task: ActiveTask, status: str, result: str, conv: ConvInfo | None, finished_at: float) -> None:
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "repo": task.repo,
                "numero": task.number,
                "tipo": task.kind,
                "rol": task.role,
                "motor": task.engine,
                "disparador": task.trigger,
                "inicio": iso(task.started_at),
                "fin": iso(finished_at),
                "duracion_min": f"{(finished_at - task.started_at) / 60:.1f}",
                "estado_final": status,
                "resultado": result,
                "tokens_entrada": conv.prompt_tokens if conv else 0,
                "tokens_salida": conv.completion_tokens if conv else 0,
                "tokens_cache": conv.cache_read_tokens if conv else 0,
                "costo_estimado_usd": f"{conv.cost_usd if conv else 0.0:.4f}",
                "conversacion": task.conversation_id,
            })

    def read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


def _max_in_window(rows: list[dict[str, str]], hours: int = 5) -> int:
    starts = sorted(datetime.fromisoformat(r["inicio"]).timestamp() for r in rows)
    best = left = 0
    for right, ts in enumerate(starts):
        while ts - starts[left] >= hours * 3600:
            left += 1
        best = max(best, right - left + 1)
    return best


def summarize(rows: list[dict[str, str]], merged: Mapping[tuple[str, int], bool]) -> str:
    lines = [
        "## Por motor",
        "",
        "| motor | tareas | máx. en 5 h | min. promedio | tokens entrada | tokens salida | costo estimado USD |",
        "|---|---|---|---|---|---|---|",
    ]
    for engine in sorted({r["motor"] for r in rows}):
        rs = [r for r in rows if r["motor"] == engine]
        avg = sum(float(r["duracion_min"]) for r in rs) / len(rs)
        tokens_in = sum(int(r["tokens_entrada"]) for r in rs)
        tokens_out = sum(int(r["tokens_salida"]) for r in rs)
        cost = sum(float(r["costo_estimado_usd"]) for r in rs)
        lines.append(
            f"| {engine} | {len(rs)} | {_max_in_window(rs)} | {avg:.1f} | {tokens_in} | {tokens_out} | {cost:.2f} |"
        )
    lines += ["", "## Por resultado", "", "| resultado | cantidad |", "|---|---|"]
    for result, count in sorted(Counter(r["resultado"] for r in rows).items()):
        lines.append(f"| {result} | {count} |")
    lines += ["", "## PRs revisados", "", "| repo | PR | mergeado |", "|---|---|---|"]
    for (repo, number), is_merged in sorted(merged.items()):
        lines.append(f"| {repo} | #{number} | {'sí' if is_merged else 'no'} |")
    return "\n".join(lines) + "\n"
