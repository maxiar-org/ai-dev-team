"""HTML de la vista de estado (fase 5b): render(View, rango) -> str, pura. Diseño: canvas de Claude Design."""

from __future__ import annotations

from html import escape

from .charts import day_label, fmt_hours, hbars, stacked_bars, strip_html
from .summary import render_summary
from .view import AGE_MARK, COLUMNS, View

RANGES = ("7", "30")
FONTS = "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"

ICONS = {
    "ok": '<svg class="ic" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="#0ca30c"/>'
          '<path d="M4.8 8.2l2.2 2.2 4.2-4.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "warn": '<svg class="ic" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5l7 12.5H1z" fill="#fab219"/>'
            '<path d="M8 6v3.6" stroke="#0b0b0b" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.8" r="1" fill="#0b0b0b"/></svg>',
    "serious": '<svg class="ic" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="#ec835a"/>'
               '<path d="M8 4.5V8l2.4 1.6" fill="none" stroke="#0b0b0b" stroke-width="1.6" stroke-linecap="round"/></svg>',
    "critical": '<svg class="ic" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="#d03b3b"/>'
                '<path d="M8 4.2v4.6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.4" r="1" fill="#fff"/></svg>',
}
LEVEL_ICON = {"ok": "ok", "advertencia": "warn", "critico": "critical"}

CSS = """
:root{--bg:#f3f2ee;--card:#fcfcfb;--line:#e2e1db;--ink:#0b0b0b;--ink2:#52514e;--muted:#6b6a65;--track:#ecebe6;--chip:#f0efea;
--btn-bg:#0b0b0b;--btn-ink:#fcfcfb;--c-claude:#eb6834;--c-codex:#1baf7a;--c-gemini:#2a78d6;--serious:#ec835a;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--card:#1a1a19;--line:#31312d;--ink:#ffffff;--ink2:#c3c2b7;--muted:#9b9a90;
--track:#2a2a27;--chip:#232321;--btn-bg:#ffffff;--btn-ink:#1a1a19;--c-claude:#d95926;--c-codex:#199e70;--c-gemini:#3987e5}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Geist,system-ui,sans-serif;padding:28px 16px 40px}
.wrap{max-width:1360px;margin:0 auto;display:flex;flex-direction:column;gap:24px}
a{color:inherit}.mono{font-family:"Geist Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace}.muted{color:var(--muted);font-size:13px}.ink2{color:var(--ink2)}
.bad{color:#d03b3b}.warn{color:var(--ink2)}
header.top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px}
.eyebrow{font-size:13px;color:var(--muted)}
h1{margin:0;font-size:30px;line-height:1.15;font-weight:650;letter-spacing:-.02em}
h2{margin:0;font-size:18px;font-weight:650}h3{margin:0;font-size:14px;font-weight:600}
.pills{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.pill{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:0 12px;border-radius:999px;background:var(--card);border:1px solid var(--line);font-size:13px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 18px;border-radius:10px;border:0;background:var(--btn-bg);color:var(--btn-ink);font:inherit;font-size:14px;font-weight:600;cursor:pointer;text-decoration:none}
.btn-line{display:inline-flex;align-items:center;min-height:36px;padding:0 14px;border-radius:8px;border:1px solid var(--line);color:var(--ink);font-size:13px;font-weight:600;text-decoration:none;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:14px;min-width:0}
.sec-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;padding:14px 0;border-top:1px solid var(--line)}
.row .kind{display:inline-flex;align-items:center;gap:6px;min-width:150px;font-size:13px;font-weight:600}
.row .what{flex:999 1 320px;min-width:0;display:flex;flex-direction:column;gap:3px}
.row .title{font-size:15px;font-weight:600}.row .sub{font-size:13px;color:var(--ink2)}
.row .age{font-size:13px;color:var(--muted);min-width:84px;font-variant-numeric:tabular-nums}
.ic{flex-shrink:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px}
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:14px;font-size:12px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;flex-shrink:0}
.sw.out{background:repeating-linear-gradient(135deg,var(--serious) 0 2px,transparent 2px 5px);border:1px solid var(--serious)}
.sw.free{background:var(--track)}.sw.work{background:var(--ink2)}
.slot-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.slot-name{display:flex;align-items:center;gap:10px;min-width:0}.slot-name .mono{font-size:15px;font-weight:500}
.slot-bar{width:12px;height:28px;border-radius:3px;flex-shrink:0}
.status{display:inline-flex;align-items:center;gap:6px;flex-shrink:0;min-height:28px;padding:0 10px;border-radius:999px;background:var(--chip);font-size:12px;font-weight:600}
.dot{width:8px;height:8px;border-radius:50%}
.strip{display:grid;grid-template-columns:repeat(24,minmax(0,1fr));gap:2px;height:22px}
.strip span{border-radius:2px;background:var(--track)}
.strip span.out{background:repeating-linear-gradient(135deg,var(--serious) 0 2px,transparent 2px 5px);border:1px solid var(--serious)}
.strip-axis{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
.nums{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;border-top:1px solid var(--line);padding-top:12px}
.num{display:flex;flex-direction:column;gap:2px}.num b{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}.num span{font-size:12px;color:var(--muted)}
.foot{font-size:12px;color:var(--ink2)}
.split{display:flex;flex-wrap:wrap;gap:16px;align-items:stretch}.split>.wide{flex:999 1 560px}.split>.narrow{flex:1 1 340px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;text-align:right;font-variant-numeric:tabular-nums;vertical-align:top}
thead th{color:var(--muted);font-weight:500;white-space:nowrap}
tbody tr{border-top:1px solid var(--line)}
th.l,td.l{text-align:left;font-weight:400}
td.n{font-size:15px;font-weight:600}td.zero{color:var(--muted)}
td.hot{font-weight:700;text-decoration:underline;text-decoration-color:#fab219;text-decoration-thickness:3px;text-underline-offset:5px}
.prog{display:flex;align-items:center;gap:8px;margin-top:6px;min-width:200px}
.prog .track{flex:1;height:6px;border-radius:3px;background:var(--track);overflow:hidden}
.prog .fill{height:100%;border-radius:3px;background:var(--ink2)}
details summary{cursor:pointer;font-size:12px;color:var(--ink2);margin-top:6px;min-height:24px}
.items{list-style:none;margin:6px 0 0;padding:0;font-size:12px}.items li{padding:3px 0}
.dep{display:flex;align-items:center;gap:10px;padding:10px 0;border-top:1px solid var(--line)}
.dep .what{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.dep b{font-size:14px;font-weight:600}.dep .sub{font-size:12px;color:var(--ink2)}
.dep .st{font-size:12px;font-weight:600;white-space:nowrap}
.seg-ctl{display:inline-flex;padding:3px;border-radius:10px;background:var(--chip);border:1px solid var(--line)}
.seg-ctl a{display:inline-flex;align-items:center;min-height:38px;padding:0 14px;border-radius:8px;font-size:13px;font-weight:600;color:var(--ink2);text-decoration:none}
.seg-ctl a[aria-current]{background:var(--card);color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:12px}
.tile{border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.tile b{font-size:26px;font-weight:650;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile span{font-size:12px;color:var(--ink2)}.tile .lbl{color:var(--muted)}
.charts{display:flex;flex-wrap:wrap;gap:24px}.charts>.wide{flex:999 1 520px;min-width:0}.charts>.narrow{flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:20px}
figure{margin:0;display:flex;flex-direction:column;gap:12px;min-width:0}figcaption{font-size:14px;font-weight:600}
.chart{display:flex;gap:8px}
.yaxis{display:flex;flex-direction:column;justify-content:space-between;font-size:11px;color:var(--muted);text-align:right;min-width:32px;font-variant-numeric:tabular-nums}
.yaxis span{line-height:0}
.plot{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
.area{position:relative}
.grid-lines{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:space-between}
.grid-lines span{border-top:1px solid var(--line)}.grid-lines span:last-child{border-top-color:var(--ink2)}
.bars{position:absolute;inset:0;display:flex;align-items:flex-end;padding:0 4px}
.bar{flex:1;min-width:0;height:100%;display:flex;flex-direction:column-reverse;gap:2px}
.bar .seg{display:block;flex-shrink:0}.bar .top{border-radius:4px 4px 0 0}
.xaxis{display:flex;padding:0 4px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.xaxis span{flex:1;min-width:0;text-align:center;white-space:nowrap}
.hbar{display:flex;flex-direction:column;gap:5px}
.hbar .top-line{display:flex;justify-content:space-between;gap:8px;font-size:12px}
.hbar .track{height:12px;border-radius:4px;background:var(--track)}.hbar .fill{height:100%;border-radius:4px}
.kv{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.kv b{font-variant-numeric:tabular-nums}
.alert{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:10px;background:var(--chip);font-size:13px;line-height:1.45}
.prose{max-width:72ch;font-size:15px;line-height:1.6}.prose h3{margin:12px 0 4px}
a.pill{text-decoration:none}a.pill:hover{border-color:var(--ink2)}
.links{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;margin-top:4px}.links a{display:inline-flex;align-items:center;gap:4px}
html{scroll-behavior:smooth}#resumen{scroll-margin-top:16px}
footer{font-size:12px;color:var(--muted)}
"""

_APP_STATES = {"running": "Corriendo", "exited": "Detenida", "restarting": "Reiniciando", "starting": "Arrancando",
               "degraded": "Degradada", "stopped": "Detenida"}
_APP_HEALTH = {"healthy": "sana", "unhealthy": "con fallas", "unknown": "sin healthcheck"}


def _app_status(status: str) -> tuple[str, str]:
    """Traduce el estado de Coolify (`<estado>:<salud>`, p. ej. `running:unknown`) a clase CSS y texto legible."""
    state, _, health = status.partition(":")
    ok = state == "running" and health != "unhealthy"
    text = _APP_STATES.get(state, state or "desconocido")
    if health:
        text += f" ({_APP_HEALTH.get(health, health)})"
    return ("ok" if ok else "bad"), text


def _a(url: str | None, text: str, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{escape(url or "#", quote=True)}">{escape(text)}</a>' if url else escape(text)


def _err(view: View, *sections: str) -> str:
    return "".join(f'<p class="bad">sin datos ({escape(view.errors[s])})</p>' for s in sections if s in view.errors)


def _age(seconds: float | None) -> str:
    if seconds is None:
        return ""
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    return f"hace {hours} h" if hours < 48 else f"hace {hours // 24} d"


def _dur(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{round(seconds / 60)} min" if seconds < 3600 else fmt_hours(round(seconds / 3600, 1))


def _usd(x: float) -> str:
    return f"USD {x:.0f}" if x >= 10 else "USD " + f"{x:.2f}".replace(".", ",")


CHECK_NAMES = {"canvas": "Canvas", "dispatcher": "Dispatcher", "tunel": "Túnel", "coolify": "Coolify"}


def _header(view: View) -> str:
    pills = []
    for c in view.health:
        inner = f'{ICONS["ok" if c.ok else "critical"]}{escape(CHECK_NAMES.get(c.name, c.name))}'
        title = escape(c.detail, quote=True)
        link = view.health_links.get(c.name.lower())
        pills.append(f'<a class="pill" href="{escape(link, quote=True)}" title="{title}">{inner}</a>' if link
                     else f'<span class="pill" title="{title}">{inner}</span>')
    running = (view.summary or {}).get("status") == "running"
    button = "" if running else '<form method="post" action="/resumen"><button type="submit" class="btn">Pedir resumen</button></form>'
    return (f'<header class="top"><div><div class="eyebrow">maxiar-org · AI Dev Team</div><h1>Estado del equipo</h1>'
            f'<div class="muted">Actualizado hace {AGE_MARK} s · se refresca cada 60 s</div></div>'
            f'<div class="pills">{"".join(pills)}<a class="btn-line" href="#resumen">Ir al resumen</a>{button}</div></header>'
            + _err(view, "salud"))


def _waiting(view: View) -> str:
    rows = []
    for h in sorted(view.human, key=lambda x: -(x.get("age") or 0)):
        note = f'<span class="sub">{escape(h["note"][:300])}</span>' if h.get("note") else ""
        rows.append(f'<div class="row"><span class="kind">{ICONS["critical"]}Decidir</span><div class="what">'
                    f'<span class="title"><span class="mono ink2">{escape(h["repo"])} #{h["number"]}</span> · {escape(h["title"])}</span>'
                    f'{note}</div><span class="age">{_age(h.get("age"))}</span>{_a(h["url"], "Abrir en GitHub", "btn-line")}</div>')
    for i, w in enumerate(view.waiting, 1):
        bits = [{"success": "CI aprobado", "failure": "CI con fallas", "pending": "CI corriendo"}.get(w["ci"], "")]
        if not w["clean"]:
            bits.append("tiene conflictos")
        if w.get("issue"):
            bits.append(_a(w.get("issue_url"), f"issue #{w['issue']}"))
        if w.get("preview"):
            bits.append(_a(w["preview"], "preview"))
        warns = "".join(f'<span class="sub">{ICONS["warn"]} {escape(x)}</span>' for x in w["warnings"])
        rows.append(f'<div class="row"><span class="kind">{ICONS["warn"]}Revisar y mergear · {i}</span><div class="what">'
                    f'<span class="title"><span class="mono ink2">{escape(w["repo"])} PR #{w["number"]}</span> · {escape(w["title"])}</span>'
                    f'<span class="sub">{" · ".join(b for b in bits if b)}</span>{warns}</div>'
                    f'<span class="age">{_age(w.get("age"))}</span>{_a(w["url"], "Abrir en GitHub", "btn-line")}</div>')
    for a in view.alerts:
        rows.append(f'<div class="row"><span class="kind">{ICONS["critical"]}Operación</span><div class="what">'
                    f'<span class="title">{escape(a["title"])}</span></div><span class="age"></span>'
                    f'{_a(a["url"], "Abrir en GitHub", "btn-line")}</div>')
    empty = '<p class="muted">Nada pendiente.</p>' if not rows and "github" not in view.errors else ""
    return (f'<section class="card" aria-labelledby="h-espera"><div class="sec-head"><h2 id="h-espera">Te esperan'
            f' <span class="muted">· {len(rows)}</span></h2><span class="muted">Nada avanza hasta que respondas.</span></div>'
            f'{_err(view, "github")}{empty}<div>{"".join(rows)}</div></section>')


def _team(view: View) -> str:
    cards = []
    for s in view.slots:
        badge = {"trabajando": f'<span class="dot" style="background:var(--c-{s["engine"]})"></span>',
                 "libre": ICONS["ok"], "sin_cupo": ICONS["serious"]}[s["status"]]
        worked = sum(1 for c in s["cells"] if c["state"] == "trabajando")
        out = sum(1 for c in s["cells"] if c["state"] == "sin_cupo")
        aria = f'{s["name"]}: {worked} horas trabajando y {out} sin cupo en las últimas 24 horas'
        cards.append(
            f'<article class="card"><div class="slot-head"><div class="slot-name">'
            f'<span class="slot-bar" style="background:var(--c-{s["engine"]})"></span><div><div class="mono">{escape(s["name"])}</div>'
            f'<div class="muted">{escape(s["label"])}</div></div></div><span class="status">{badge}{escape(s["status_text"])}</span></div>'
            f'<div class="ink2" style="font-size:13px">{escape(s["detail"])}</div>'
            f'<div>{strip_html(s["cells"], s["engine"], aria)}<div class="strip-axis"><span>hace 24 h</span><span>ahora</span></div></div>'
            f'<div class="nums"><div class="num"><b>{s["tasks"]}</b><span>tareas en 24 h</span></div>'
            f'<div class="num"><b>{fmt_hours(s["hours"])}</b><span>trabajando</span></div>'
            f'<div class="num"><b>{fmt_hours(s["exhausted"])}</b><span>sin cupo</span></div></div>'
            f'<div class="foot">{escape(s["footer"])}</div></article>')
    legend = ('<div class="legend"><span><span class="sw work"></span>Trabajando (color del puesto)</span>'
              '<span><span class="sw out"></span>Sin cupo</span><span><span class="sw free"></span>Libre</span></div>')
    return (f'<section aria-labelledby="h-equipo" style="display:flex;flex-direction:column;gap:12px"><div class="sec-head">'
            f'<h2 id="h-equipo">Equipo</h2>{legend}</div>{_err(view, "dispatcher")}<div class="grid">{"".join(cards)}</div></section>')


def _projects(view: View) -> str:
    head = "".join(f'<th scope="col">{c}</th>' for c in COLUMNS)
    body = []
    for p in view.projects:
        epic = ""
        if p["epic"]:
            e = p["epic"]
            pct = round(100 * e["done"] / e["total"]) if e["total"] else 0
            epic = (f'<div class="prog"><div class="track"><div class="fill" style="width:{pct}%"></div></div>'
                    f'<span class="ink2" style="font-size:12px;white-space:nowrap">{e["done"]} de {e["total"]}</span></div>'
                    f'<div class="muted" style="font-size:12px">{_a(e["url"], e["title"])}</div>')
        items = "".join(f'<li>{_a(i["url"], "#" + str(i["number"]) + " " + i["title"])} <span class="muted">· {escape(i["stage"])}</span></li>'
                        for i in p["items"])
        details = f'<details><summary>Ver issues ({len(p["items"])})</summary><ul class="items">{items}</ul></details>' if items else ""
        cells = []
        for c in COLUMNS:
            n = p["counts"][c]
            cls = "zero" if n == 0 else ("n hot" if c == "Te espera" else "n")
            cells.append(f'<td class="{cls}">{n if n else "·"}</td>')
        links = [_a(x["url"], x["title"]) for x in p["views"]]
        links += [f'{ICONS["ok" if _app_status(x["status"])[0] == "ok" else "critical"]}'
                  f'{_a(x["url"], x["url"].removeprefix("https://"))}' for x in p["sites"]]
        links_html = f'<div class="links">{"".join(f"<span>{x}</span>" for x in links)}</div>' if links else ""
        body.append(f'<tr><th scope="row" class="l"><div class="mono" style="font-size:14px">{_a(p["url"], p["repo"])}</div>'
                    f'{links_html}{epic}{details}</th>{"".join(cells)}</tr>')
    return (f'<section class="card wide" aria-labelledby="h-proyectos"><div class="sec-head"><h2 id="h-proyectos">Proyectos</h2>'
            f'<span class="muted">Issues y PR abiertos por etapa</span></div>{_err(view, "github", "vistas")}<div class="scroll">'
            f'<table style="min-width:600px"><thead><tr><th scope="col" class="l">Proyecto y épica</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></section>')


def _deploys(view: View) -> str:
    rows = []
    for a in view.apps:
        ok, status = _app_status(a.status)
        rows.append(f'<div class="dep">{ICONS["ok" if ok == "ok" else "critical"]}<div class="what"><b>{_a(a.url, a.name)}</b>'
                    f'<span class="sub">Último deploy: {escape(a.last_deploy or "—")} ({escape(a.last_deploy_status or "—")})</span></div>'
                    f'<span class="st">{escape(status)}</span></div>')
    for p in view.previews:
        rows.append(f'<div class="dep">{ICONS["ok"]}<div class="what"><b>{_a(p["url"], p["repo"] + " · preview del PR #" + str(p["number"]))}</b></div>'
                    f'<span class="st">En línea</span></div>')
    for c in view.credentials:
        rows.append(f'<div class="dep">{ICONS[LEVEL_ICON[c["level"]]]}<div class="what"><b>{escape(c["name"])}</b>'
                    f'<span class="sub">{escape(c["text"])}</span></div></div>')
    return (f'<section class="card narrow" aria-labelledby="h-despliegues"><h2 id="h-despliegues">Despliegues y credenciales</h2>'
            f'{_err(view, "coolify")}<div>{"".join(rows)}</div></section>')


def _budget(view: View, rango: str) -> str:
    b = view.budget.get(rango)
    seg = "".join(f'<a href="?rango={r}"{" aria-current=\"page\"" if r == rango else ""}>{r} días</a>' for r in RANGES)
    head = (f'<div class="sec-head"><div><h2 id="h-consumo">Consumo y presupuesto</h2><span class="muted">De metrics.csv y '
            f'limits.csv. El costo fijo se prorratea por día.</span></div><nav class="seg-ctl" aria-label="Período">{seg}</nav></div>')
    errors = _err(view, "salud", "consumo")
    if not b:
        return f'<section class="card" aria-labelledby="h-consumo">{head}{errors}</section>'
    tiles = [("Costo estimado", _usd(b["cost"]), f'Fijo prorrateado {_usd(b["fixed"])} + {b["images"]} imágenes {_usd(b["image_cost"])}'),
             ("Issues cerrados", str(b["closed"]), f'{_usd(b["cost_per_issue"])} por issue' if b["cost_per_issue"] is not None else "sin issues cerrados"),
             ("Retrabajo", f'{b["rework"]:.1f}'.replace(".", ","), "rondas de fix y QA por issue"),
             ("Cortes por límite", str(b["cuts"]), f'{fmt_hours(b["exhausted_hours"])} sin cupo entre todos los puestos')]
    tiles_html = "".join(f'<div class="tile"><span class="lbl">{t}</span><b>{v}</b><span>{escape(s)}</span></div>' for t, v, s in tiles)
    slots = [(s["name"], s["engine"]) for s in view.slots] or [(e["slot"], e["engine"]) for e in b["exhausted"]]
    legend = "".join(f'<span><span class="sw" style="background:var(--c-{eng})"></span><span class="mono">{escape(n)}</span></span>'
                     for n, eng in slots)
    table_rows = "".join(
        f'<tr><th scope="row" class="l">{day_label(d["date"], False)}</th>'
        + "".join(f'<td>{fmt_hours(d["minutes"].get(n, 0.0) / 60)}</td>' for n, _ in slots)
        + f'<td><b>{fmt_hours(sum(d["minutes"].values()) / 60)}</b></td></tr>' for d in reversed(b["daily"]))
    table = (f'<details><summary class="btn-line" style="display:inline-flex">Ver como tabla</summary><div class="scroll" '
             f'style="max-height:260px;overflow-y:auto;margin-top:8px"><table><thead><tr><th scope="col" class="l">Día</th>'
             + "".join(f'<th scope="col">{escape(n)}</th>' for n, _ in slots)
             + f'<th scope="col">Total</th></tr></thead><tbody>{table_rows}</tbody></table></div></details>')
    top = max((e["hours"] for e in b["exhausted"]), default=0) or 1
    hb = hbars([{"label": e["slot"], "value": f'{fmt_hours(e["hours"])} · {e["cuts"]} {"corte" if e["cuts"] == 1 else "cortes"}',
                 "fraction": e["hours"] / top, "engine": e["engine"], "title": f'{e["slot"]}: {fmt_hours(e["hours"])} sin cupo'}
                for e in b["exhausted"]])
    f = b["flow"]
    flow = "".join(f'<div class="kv"><span class="ink2">{t}</span><b>{_dur(f[k])}</b></div>' for t, k in
                   (("Issue a PR", "issue_to_pr"), ("PR a merge (incluye tu review)", "pr_to_merge"), ("Total", "total")))
    alerts = "".join(f'<div class="alert">{ICONS["warn"]}<div>{escape(a)}</div></div>' for a in b["alerts"]) \
        or '<p class="muted">Nada para decidir.</p>'
    aria = f'Barras apiladas de horas de trabajo por día en los últimos {b["days"]} días, por puesto. La tabla tiene los valores.'
    proj_rows = "".join(
        f'<tr><th scope="row" class="l mono">{escape(p["repo"])}</th><td>{fmt_hours(p["hours"])}</td><td>{p["images"]}</td>'
        f'<td><b>{_usd(p["cost"])}</b></td><td>{p["closed"]}</td>'
        f'<td>{_usd(p["cost_per_issue"]) if p["cost_per_issue"] is not None else "—"}</td></tr>' for p in b["by_project"])
    by_project = (f'<div style="display:flex;flex-direction:column;gap:10px"><h3>Costo por proyecto</h3><span class="muted">El fijo de '
                  f'cada puesto se reparte según los minutos que trabajó en cada proyecto; el de un puesto sin trabajo queda sin asignar.'
                  f'</span><div class="scroll"><table style="min-width:520px"><thead><tr><th scope="col" class="l">Proyecto</th>'
                  f'<th scope="col">Horas</th><th scope="col">Imágenes</th><th scope="col">Costo</th><th scope="col">Issues cerrados</th>'
                  f'<th scope="col">Costo por issue</th></tr></thead><tbody>{proj_rows}</tbody></table></div></div>') if b["by_project"] else ""
    return (f'<section class="card" aria-labelledby="h-consumo">{head}{errors}<div class="tiles">{tiles_html}</div>'
            f'<div class="charts"><figure class="wide"><div class="sec-head"><figcaption>Horas de trabajo por día y puesto</figcaption>'
            f'<div class="legend">{legend}</div></div><div role="img" aria-label="{escape(aria, quote=True)}">'
            f'{stacked_bars(b["daily"], slots)}</div>{table}</figure>'
            f'<div class="narrow"><figure><figcaption>Horas sin cupo por puesto</figcaption>{hb}</figure>'
            f'<div style="display:flex;flex-direction:column;gap:10px"><h3>Tiempos de flujo <span class="muted">· mediana</span></h3>{flow}</div></div></div>'
            f'{by_project}<div style="display:flex;flex-direction:column;gap:10px"><h3>Para decidir</h3>{alerts}</div></section>')


def render(view: View, rango: str = "7") -> str:
    rango = rango if rango in RANGES else "7"
    reload_ms = 10_000 if (view.summary or {}).get("status") == "running" else 60_000
    return "".join([
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>Estado · AI Dev Team</title><link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="stylesheet" href="{FONTS}"><style>{CSS}</style></head><body><div class="wrap">',
        _header(view), _waiting(view), _team(view),
        f'<div class="split">{_projects(view)}{_deploys(view)}</div>',
        _budget(view, rango),
        render_summary(view.summary, view.errors.get("resumen"), view.updated),
        '<footer>AI Dev Team · vista de estado</footer></div>',
        f'<script>setInterval(function(){{if(!document.querySelector("details[open]"))location.reload()}},{reload_ms});</script>',
        '</body></html>',
    ])


def render_all(view: View) -> dict[str, str]:
    return {r: render(view, r) for r in RANGES}
