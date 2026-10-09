"""Resumen del operador: datos del período (para el LLM) y render seguro del markdown que devuelve."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import escape

NOTICE_MARK = "__AVISO__"  # el servidor lo reemplaza por el aviso de error de un POST (o nada)
DISPLAY_TZ = timezone(timedelta(hours=-3))  # hora de Argentina (sin horario de verano)
LINK_RE = re.compile(r"\[([^\]]+)\]\((https://[^)\s&\"]+(?:&amp;[^)\s&\"]+)*)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
OL_RE = re.compile(r"^\d+\.\s+")


def _ts(value: str | None) -> float | None:
    try:
        return datetime.fromisoformat(value).timestamp() if value else None
    except ValueError:
        return None


def _fmt(value: str | None) -> str:
    ts = _ts(value)
    return datetime.fromtimestamp(ts, tz=DISPLAY_TZ).strftime("%d/%m %H:%M") if ts is not None else "—"


def period_data(view, since: str, now: float, merged: list, closed: list, ops: list, metrics: list[dict]) -> dict:
    since_ts = _ts(since) or 0.0
    tareas = [{"repo": r.get("repo"), "numero": r.get("numero"), "rol": r.get("rol"), "motor": r.get("motor"),
               "resultado": r.get("resultado"), "minutos": r.get("duracion_min")}
              for r in metrics if (_ts(r.get("fin")) or 0.0) >= since_ts]
    return {
        "desde": since,
        "ahora": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "espera_a_eduardo": view.waiting,
        "necesita_humano": view.human,
        "alertas_abiertas": view.alerts,
        "tokens": view.tokens,
        "en_curso": view.work,
        "despliegues": [{"name": a.name, "url": a.url, "status": a.status, "last_deploy": a.last_deploy} for a in view.apps],
        "salud": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in view.health],
        "consumo": view.usage,
        "mergeados": merged,
        "cerrados": closed,
        "ops_del_periodo": ops,
        "tareas": tareas,
    }


def _inline(text: str) -> str:
    t = escape(text, quote=True)
    t = LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    return BOLD_RE.sub(r"<b>\1</b>", t)


def md_to_html(md: str) -> str:
    out: list[str] = []
    open_list: str | None = None

    def close() -> None:
        nonlocal open_list
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None

    for raw in (md or "").splitlines():
        line = raw.strip()
        kind, text = None, line
        if line.startswith(("- ", "* ")):
            kind, text = "ul", line[2:]
        elif OL_RE.match(line):
            kind, text = "ol", OL_RE.sub("", line, count=1)
        if kind:
            if open_list != kind:
                close()
                out.append(f"<{kind}>")
                open_list = kind
            out.append(f"<li>{_inline(text)}</li>")
            continue
        close()
        if not line:
            continue
        if line.startswith("### "):
            out.append(f"<h4>{_inline(line[4:])}</h4>")
        elif line.startswith("## ") or line.startswith("# "):
            out.append(f"<h3>{_inline(line.lstrip('#').strip())}</h3>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
    close()
    return "".join(out)


def render_summary(summary: dict | None, error: str | None, now: float) -> str:
    out = ["<h2>🤖 Resumen del operador</h2>", NOTICE_MARK]
    if error:
        out.append(f'<p class="bad">⚠️ sin datos ({escape(error)})</p>')
    if summary:
        if summary.get("error"):
            out.append(f'<p class="bad">⚠️ el último pedido falló: {escape(str(summary["error"])[:300])}</p>')
        last = summary.get("last")
        if last:
            out.append(f'<div class="card"><div class="muted">Generado {_fmt(last.get("generated_at"))} · '
                       f'cubre desde {_fmt(last.get("since"))}</div>{md_to_html(last.get("markdown", ""))}</div>')
        else:
            out.append('<p class="muted">Todavía no hay resúmenes.</p>')
    if summary and summary.get("status") == "running":
        started = summary.get("started_at") or now
        out.append(f'<p class="warn">⏳ generando… hace {int(now - started)} s</p>')
    else:
        out.append('<form method="post" action="/resumen"><button type="submit">Pedir resumen</button></form>')
    return "".join(out)
