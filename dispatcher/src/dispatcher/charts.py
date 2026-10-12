"""Gráficos de la vista de estado como HTML y CSS (sin JS). Funciones puras; los estilos están en render.CSS."""

from __future__ import annotations

import math
from datetime import date
from html import escape

DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def scale_top(max_hours: float) -> int:
    top = max(2, math.ceil(max_hours))
    return top + top % 2


def fmt_hours(h: float) -> str:
    if h <= 0:
        return "0 h"
    if float(h).is_integer():
        return f"{int(h)} h"
    return f"{h:.1f}".replace(".", ",") + " h"


def day_label(d: date, short: bool) -> str:
    base = f"{DAYS[d.weekday()]} {d.day}"
    return base if short else f"{base} {MONTHS[d.month - 1]}"


def stacked_bars(daily: list[dict], slots: list[tuple[str, str]], height: int = 200) -> str:
    top = scale_top(max((sum(d["minutes"].values()) / 60 for d in daily), default=0))
    gap = 14 if len(daily) <= 7 else 3
    ticks = "".join(f"<span>{'0' if i == 0 else fmt_hours(top * i / 4)}</span>" for i in range(4, -1, -1))
    bars, labels = [], []
    for k, d in enumerate(daily):
        present = [(eng, d["minutes"].get(name, 0.0)) for name, eng in slots if d["minutes"].get(name, 0.0) > 0]
        segs = []
        for j, (eng, minutes) in enumerate(present):
            px = max(1, round(height * (minutes / 60) / top) - 2)
            cls = "seg top" if j == len(present) - 1 else "seg"
            segs.append(f'<span class="{cls}" style="height:{px}px;background:var(--c-{eng})"></span>')
        title = day_label(d["date"], True) + " · " + " · ".join(
            f"{name} {fmt_hours(d['minutes'].get(name, 0.0) / 60)}" for name, _ in slots)
        bars.append(f'<div class="bar" title="{escape(title, quote=True)}">{"".join(segs)}</div>')
        from_end = len(daily) - 1 - k
        text = day_label(d["date"], True) if len(daily) <= 7 else (str(d["date"].day) if from_end % 5 == 0 else "")
        labels.append(f'<span class="xl">{text}</span>')
    return (f'<div class="chart"><div class="yaxis" style="height:{height}px">{ticks}</div><div class="plot">'
            f'<div class="area" style="height:{height}px"><div class="grid-lines" aria-hidden="true">'
            + "<span></span>" * 5 + f'</div><div class="bars" style="gap:{gap}px">{"".join(bars)}</div></div>'
            f'<div class="xaxis" style="gap:{gap}px">{"".join(labels)}</div></div></div>')


def hbars(rows: list[dict]) -> str:
    out = []
    for r in rows:
        width = round(100 * max(0.0, min(1.0, r["fraction"])))
        out.append(f'<div class="hbar"><div class="top-line"><span class="mono">{escape(r["label"])}</span>'
                   f'<span class="ink2">{escape(r["value"])}</span></div>'
                   f'<div class="track" title="{escape(r["title"], quote=True)}"><div class="fill" '
                   f'style="width:{width}%;background:var(--c-{r["engine"]})"></div></div></div>')
    return "".join(out)


def strip_html(cells: list[dict], engine: str, aria: str) -> str:
    spans = []
    for c in cells:
        title = escape(c["title"], quote=True)
        if c["state"] == "trabajando":
            spans.append(f'<span title="{title}" style="background:var(--c-{engine})"></span>')
        elif c["state"] == "sin_cupo":
            spans.append(f'<span title="{title}" class="out"></span>')
        else:
            spans.append(f'<span title="{title}"></span>')
    return f'<div class="strip" role="img" aria-label="{escape(aria, quote=True)}">{"".join(spans)}</div>'
