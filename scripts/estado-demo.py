"""Renderiza la vista de estado con datos de ejemplo, para compararla con el diseño sin la mini-PC.

Uso: cd dispatcher && uv run python ../scripts/estado-demo.py /ruta/de/salida
Escribe estado-7.html y estado-30.html.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dispatcher.models import Item, Slot
from dispatcher.render import render_all
from dispatcher.view import AppInfo, PRInfo, Snapshot, build_view
from dispatcher.watchdog import Check

NOW = datetime(2026, 10, 12, 9, 4, tzinfo=timezone.utc).timestamp()
SLOTS = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))


def iso(hours_ago: float) -> str:
    return datetime.fromtimestamp(NOW - hours_ago * 3600, tz=timezone.utc).isoformat()


def metrics() -> list[dict]:
    rows = []
    for d in range(30):
        for slot, minutes, every in (("claude-senior", 25, 3), ("codex-senior", 35, 2), ("gemini", 15, 5 if d < 3 else 99)):
            for h in range(0, 24, every):
                if (d * 7 + h) % 3:
                    continue
                start = d * 24 + h + 0.3
                rows.append({"repo": "nikito", "numero": str(20 + d), "rol": ("dev", "review", "qa", "fix")[h % 4], "tipo": "issue",
                             "motor": slot.split("-")[0], "puesto": slot, "inicio": iso(start), "fin": iso(start - minutes / 60),
                             "duracion_min": str(minutes), "resultado": "pr_abierto", "imagenes_gemini": "2" if slot == "gemini" else "0"})
    return rows


def main(out: Path) -> None:
    snap = Snapshot(
        now=NOW, org="maxiar-org", repos=("nikito", "agent-playground", "ai-dev-team"), slots=SLOTS, tz="America/Argentina/Buenos_Aires",
        slot_costs={"claude-senior": 100.0, "codex-senior": 200.0, "gemini": 20.0},
        slot_labels={"claude-senior": "Claude Max 5x · arquitectura y tareas grandes", "codex-senior": "Codex Pro · dev S/M e imágenes",
                     "gemini": "Gemini Pro · QA, respaldo de dev e imágenes"},
        issues=[Item("nikito", 11, "issue", "Épica: Fase 1 — Vertical slice matemático", "", frozenset({"epic"}), sub_issues=(4, 9)),
                Item("nikito", 23, "issue", "Motor de ejercicios de sumas y restas", "", frozenset({"needs:human"}), updated_at=iso(0.7)),
                Item("nikito", 5, "issue", "Pantalla de inicio", "", frozenset({"agent:working"})),
                Item("nikito", 6, "issue", "Mis estrellas", "", frozenset({"agent:dev"})),
                Item("nikito", 7, "issue", "Sonidos", "", frozenset())],
        prs=[PRInfo("nikito", 21, "Design system aplicado a la app", "https://github.com/maxiar-org/nikito/pull/21", frozenset(),
                    "Closes #3", "agent/3-ds", "clean", "success", ("lib/theme.dart",), iso(5)),
             PRInfo("nikito", 22, "Ilustraciones con el avatar nuevo de Nico", "https://github.com/maxiar-org/nikito/pull/22", frozenset(),
                    "Closes #4", "agent/4-img", "clean", "success", ("assets/a.png",), iso(3)),
             PRInfo("agent-playground", 8, "Agregar wakeup.sh", "u", frozenset({"agent:qa"}))],
        active={"nikito#5": {"role": "dev", "engine": "claude", "slot": "claude-senior", "started_at": NOW - 120}},
        exhausted={"gemini": NOW + 2 * 3600},
        human_notes={"nikito#23": "Pidió ayuda: QA sigue fallando después de 3 rondas de fix."},
        repo_projects={"nikito": [{"title": "NIKITO Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/3"}]},
        health_links={"canvas": "https://canvas.example", "coolify": "https://coolify.example"},
        checks=[Check("Canvas", True, "ok"), Check("Dispatcher", True, "latido hace 20 s"), Check("Túnel", True, "ok"),
                Check("Coolify", True, "ok")],
        apps=[AppInfo("nikito-web", "maxiar-org/nikito", "https://nikito.maxiar.dev", "running:healthy", "2026-10-12 04:00", "finished")],
        expiries={"GITHUB_TOKEN": date(2026, 11, 2), "CLAUDE_CODE_OAUTH_TOKEN": date(2027, 10, 11)},
        metrics=metrics(),
        limits=[{"puesto": "codex-senior", "detectado": iso(30 + 24 * d), "hasta": iso(27 + 24 * d)} for d in (0, 1, 3)]
        + [{"puesto": "gemini", "detectado": iso(1), "hasta": iso(-2)}],
        closed=[{"repo": "nikito", "number": n, "closed_at": iso(n * 9), "labels": []} for n in range(1, 15)],
        merged=[{"repo": "nikito", "number": 30 + n, "closes": 20 + n, "created_at": iso(n * 24 + 6), "merged_at": iso(n * 24)}
                for n in range(1, 12)],
    )
    out.mkdir(parents=True, exist_ok=True)
    for rango, html in render_all(build_view(snap)).items():
        (out / f"estado-{rango}.html").write_text(html.replace("__EDAD__", "12").replace("__AVISO__", ""), encoding="utf-8")
    print(f"Escribí {out}/estado-7.html y estado-30.html")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
