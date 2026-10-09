"""Vista de estado del AI Dev Team: build_view(Snapshot) -> View y render(View) -> HTML, ambas puras."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html import escape

from .decide import parse_dependencies
from .models import LABEL_DEV, LABEL_DOCS, LABEL_FIX, LABEL_HUMAN, LABEL_QA, LABEL_REVIEW, LABEL_WORKING, Item
from .watchdog import Check


@dataclass(frozen=True)
class AppInfo:
    name: str
    repo: str
    url: str
    status: str
    last_deploy: str | None = None
    last_deploy_status: str | None = None
    preview_template: str | None = None
    preview_prs: tuple[int, ...] = ()


AGENT_LABELS = frozenset({LABEL_WORKING, LABEL_REVIEW, LABEL_FIX, LABEL_QA})
CLOSES_RE = re.compile(r"(?i)\b(?:closes|fixes|resolves|cierra)\s+#(\d+)\b")
ROLE_NAMES = {"dev": "dev", "review": "review", "qa": "QA", "fix": "fix", "docs": "docs"}


@dataclass(frozen=True)
class PRInfo:
    repo: str
    number: int
    title: str
    url: str
    labels: frozenset[str]
    body: str = ""
    head_ref: str = ""
    mergeable_state: str | None = None
    ci: str = "none"
    files: tuple[str, ...] = ()


@dataclass
class Snapshot:
    now: float
    org: str = "maxiar-org"
    issues: list[Item] = field(default_factory=list)
    prs: list[PRInfo] = field(default_factory=list)
    active: dict[str, dict] = field(default_factory=dict)
    ops: list[tuple[int, str, str]] = field(default_factory=list)
    expiries: dict[str, date | None] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    apps: list[AppInfo] = field(default_factory=list)
    metrics: list[dict[str, str]] = field(default_factory=list)
    human_notes: dict[str, str] = field(default_factory=dict)
    summary: dict | None = None
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class View:
    updated: float
    waiting: list[dict] = field(default_factory=list)
    human: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    work: dict[str, list[dict]] = field(default_factory=dict)
    apps: list[AppInfo] = field(default_factory=list)
    previews: list[dict] = field(default_factory=list)
    health: list[Check] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    summary: dict | None = None


def issue_of(pr: PRInfo) -> int | None:
    m = re.match(r"agent/(\d+)-", pr.head_ref or "")
    if m:
        return int(m.group(1))
    m = CLOSES_RE.search(pr.body or "")
    return int(m.group(1)) if m else None


def awaits_human(labels: frozenset[str]) -> bool:
    """Un PR sin labels de agente ni needs:human: candidato a esperar a Eduardo (lo usa el recolector)."""
    return not (labels & AGENT_LABELS) and LABEL_HUMAN not in labels


def _ready(p: PRInfo) -> bool:
    return p.mergeable_state != "dirty" and p.ci in ("success", "none")


def merge_order(waiting: list[PRInfo], issues: list[Item]) -> list[PRInfo]:
    by_issue = {(p.repo, issue_of(p)): p for p in waiting if issue_of(p) is not None}
    bodies = {(i.repo, i.number): i.body for i in issues}
    base = sorted(waiting, key=lambda p: (0 if _ready(p) else 1, p.number, p.repo))

    def blockers(p: PRInfo) -> set[tuple[str, int]]:
        iss = issue_of(p)
        deps = parse_dependencies(bodies.get((p.repo, iss), "")) if iss is not None else ()
        found = (by_issue.get((p.repo, d)) for d in deps)
        return {(b.repo, b.number) for b in found if b is not None and b is not p}

    result: list[PRInfo] = []
    pending = list(base)
    while pending:
        done = {(p.repo, p.number) for p in result}
        pick = next((p for p in pending if blockers(p) <= done), None)
        if pick is None:  # ciclo de dependencias: se respeta el orden base
            result.extend(pending)
            break
        result.append(pick)
        pending.remove(pick)
    return result


def _preview(pr: PRInfo, apps: list[AppInfo], org: str) -> str | None:
    for a in apps:
        if a.repo in (f"{org}/{pr.repo}", pr.repo) and pr.number in a.preview_prs:
            return _preview_url(a, pr.number)
    return None


def _preview_url(app: AppInfo, number: int) -> str | None:
    tpl = app.preview_template or ""
    if "{{pr_id}}" not in tpl or "{{" in tpl.replace("{{pr_id}}", ""):  # p. ej. {{domain}}: no lo resolvemos
        return None
    return "https://" + tpl.replace("{{pr_id}}", str(number))


def _stage(labels: frozenset[str], kind: str, task: dict | None, open_deps: list[int], now: float) -> str:
    if LABEL_HUMAN in labels:
        return "necesita a Eduardo"
    if task:
        mins = int((now - float(task.get("started_at", now))) // 60)
        return f"{ROLE_NAMES.get(task.get('role'), task.get('role'))} · {task.get('engine')} · hace {mins} min"
    for label, name in ((LABEL_FIX, "fix"), (LABEL_QA, "QA"), (LABEL_REVIEW, "review")):
        if label in labels:
            return f"{name} (en cola)"
    if kind == "issue":
        if labels & {LABEL_DEV, LABEL_DOCS}:
            if open_deps:
                return "bloqueado (depende de " + ", ".join(f"#{d}" for d in open_deps) + ")"
            return "listo para agentes"
        return "backlog"
    return "espera a Eduardo"


def _usage(rows: list[dict[str, str]], now: float) -> list[dict]:
    acc: dict[str, dict] = defaultdict(lambda: {"tasks_24h": 0, "minutes_24h": 0.0, "tasks_7d": 0, "minutes_7d": 0.0})
    for r in rows:
        try:
            age = now - datetime.fromisoformat(r["inicio"]).timestamp()
            minutes = float(r.get("duracion_min") or 0)
        except (KeyError, TypeError, ValueError):  # fila incompleta (el dispatcher la está escribiendo)
            continue
        if age > 7 * 86400:
            continue
        e = acc[r.get("motor") or "?"]
        e["tasks_7d"] += 1
        e["minutes_7d"] += minutes
        if age <= 86400:
            e["tasks_24h"] += 1
            e["minutes_24h"] += minutes
    return [{"engine": k, **v} for k, v in sorted(acc.items())]


def build_view(snap: Snapshot) -> View:
    v = View(updated=snap.now, apps=snap.apps, health=snap.checks, errors=dict(snap.errors), summary=snap.summary)
    working = {(i.repo, i.number) for i in snap.issues if LABEL_WORKING in i.labels}
    active = {(r, int(n)) for r, _, n in (k.rpartition("#") for k in snap.active) if n.isdigit()}
    busy = working | active

    def in_agent_flow(p: PRInfo) -> bool:  # el agente sigue trabajando en el PR o en su issue
        return (p.repo, p.number) in busy or (p.repo, issue_of(p)) in busy

    waiting = [p for p in snap.prs if awaits_human(p.labels) and not in_agent_flow(p)]
    ordered = merge_order(waiting, snap.issues)
    seen_files: list[tuple[str, int, set[str]]] = []
    for p in ordered:
        warnings = [f"puede generar conflicto con #{n} (tocan {', '.join(sorted(f & set(p.files)))})"
                    for r, n, f in seen_files if r == p.repo and f & set(p.files)]
        seen_files.append((p.repo, p.number, set(p.files)))
        iss = issue_of(p)
        v.waiting.append({"repo": p.repo, "number": p.number, "title": p.title, "url": p.url, "ci": p.ci,
                          "clean": p.mergeable_state != "dirty", "preview": _preview(p, snap.apps, snap.org),
                          "issue": iss, "issue_url": f"https://github.com/{snap.org}/{p.repo}/issues/{iss}" if iss else None,
                          "warnings": warnings})
    for it in [*snap.issues, *snap.prs]:
        if LABEL_HUMAN in it.labels:
            url = it.url if isinstance(it, PRInfo) else f"https://github.com/{snap.org}/{it.repo}/issues/{it.number}"
            v.human.append({"repo": it.repo, "number": it.number, "title": it.title, "url": url,
                            "note": snap.human_notes.get(f"{it.repo}#{it.number}", "")})
    v.alerts = [{"title": t, "url": u} for _, t, u in snap.ops]
    today = datetime.fromtimestamp(snap.now, tz=timezone.utc).date()
    for name, exp in sorted(snap.expiries.items()):
        if exp is not None and (exp - today).days <= 30:
            v.tokens.append(f"{name} vence el {exp.isoformat()} (en {(exp - today).days} días)")
    open_issues = {(i.repo, i.number) for i in snap.issues}
    for it in sorted([*snap.issues, *snap.prs], key=lambda x: (x.repo, x.number)):
        kind = "pr" if isinstance(it, PRInfo) else "issue"
        deps = [d for d in parse_dependencies(it.body) if (it.repo, d) in open_issues] if kind == "issue" else []
        stage = _stage(it.labels, kind, snap.active.get(f"{it.repo}#{it.number}"), deps, snap.now)
        url = it.url if isinstance(it, PRInfo) else f"https://github.com/{snap.org}/{it.repo}/issues/{it.number}"
        v.work.setdefault(it.repo, []).append({"number": it.number, "kind": kind, "title": it.title, "url": url, "stage": stage})
    open_prs = {(p.repo, p.number) for p in snap.prs}
    for a in snap.apps:
        repo = a.repo.split("/")[-1]
        for n in a.preview_prs:
            url = _preview_url(a, n)
            if (repo, n) in open_prs and url:
                v.previews.append({"repo": repo, "number": n, "url": url})
    v.usage = _usage(snap.metrics, snap.now)
    return v


AGE_MARK = "__EDAD__"  # el servidor lo reemplaza por los segundos desde la recolección

CSS = """
:root{color-scheme:dark}body{font:15px/1.45 -apple-system,system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:14px;max-width:760px;margin:auto}
h1{font-size:20px;margin:4px 0 2px}h2{font-size:16px;margin:22px 0 8px;border-bottom:1px solid #30363d;padding-bottom:4px}
.muted{color:#8b949e;font-size:13px}.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:10px 12px;margin:8px 0}
.urgent{border-color:#d29922}a{color:#58a6ff;text-decoration:none}.ok{color:#3fb950}.bad{color:#f85149}.warn{color:#d29922}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:4px 2px;border-bottom:1px solid #21262d;vertical-align:top}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid #30363d;background:#238636;color:#fff}
.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;background:#21262d;margin-left:4px}
"""


def _a(url: str | None, text: str) -> str:
    return f'<a href="{escape(url or "#", quote=True)}">{escape(text)}</a>' if url else escape(text)


def _err(view: View, section: str) -> str:
    return f'<p class="bad">⚠️ sin datos ({escape(view.errors[section])})</p>' if section in view.errors else ""


def render(view: View) -> str:
    from .summary import render_summary  # import diferido: summary no depende de view, pero así queda a salvo de ciclos

    reload_s = 10 if (view.summary or {}).get("status") == "running" else 60
    out = [f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta http-equiv="refresh" content="{reload_s}"><title>Estado · AI Dev Team</title><style>{CSS}</style></head><body>',
           f'<h1>AI Dev Team</h1><div class="muted">Actualizado hace {AGE_MARK} s · se recarga cada minuto</div>']
    # 1. Qué espera de ti
    out.append("<h2>🔔 Qué espera de ti</h2>")
    out.append(_err(view, "github"))
    if "github" not in view.errors and not (view.waiting or view.human or view.alerts or view.tokens):
        out.append('<p class="ok">Nada pendiente 🎉</p>')
    for i, w in enumerate(view.waiting, 1):
        ci = {"success": '<span class="ok">CI ✓</span>', "failure": '<span class="bad">CI ✗</span>',
              "pending": '<span class="warn">CI …</span>'}.get(w["ci"], "")
        conflict = "" if w["clean"] else '<span class="warn">conflictos</span>'
        preview = f' · {_a(w["preview"], "preview")}' if w["preview"] else ""
        issue = f' · {_a(w.get("issue_url"), f"issue #{w["issue"]}")}' if w.get("issue") else ""
        warns = "".join(f'<div class="warn">⚠️ {escape(x)}</div>' for x in w["warnings"])
        out.append(f'<div class="card urgent"><b>{i}.</b> {_a(w["url"], f"{w["repo"]} #{w["number"]}: {w["title"]}")}'
                   f'<div class="muted">Revisar y mergear{issue} · {ci} {conflict}{preview}</div>{warns}</div>')
    for h in view.human:
        note = f'<div class="muted">{escape(h["note"][:300])}</div>' if h["note"] else ""
        out.append(f'<div class="card urgent">🙋 {_a(h["url"], f"{h["repo"]} #{h["number"]}: {h["title"]}")} '
                   f'<span class="tag">needs:human</span>{note}</div>')
    for a in view.alerts:
        out.append(f'<div class="card urgent">🚨 {_a(a["url"], a["title"])}</div>')
    for t in view.tokens:
        out.append(f'<div class="card urgent">🔑 {escape(t)}</div>')
    # 2. Trabajo en curso
    out.append("<h2>🛠️ Trabajo en curso</h2>")
    out.append(_err(view, "github"))
    out.append(_err(view, "dispatcher"))
    for repo, rows in sorted(view.work.items()):
        out.append(f'<div class="card"><b>{escape(repo)}</b><table>')
        for r in rows:
            out.append(f'<tr><td>{_a(r["url"], f"#{r["number"]} {r["title"]}")}</td><td class="muted">{escape(r["stage"])}</td></tr>')
        out.append("</table></div>")
    # 3. Despliegues
    out.append("<h2>🚀 Despliegues</h2>")
    out.append(_err(view, "coolify"))
    for a in view.apps:
        ok = "ok" if a.status.startswith("running") else "bad"
        out.append(f'<div class="card">{_a(a.url, a.name)} <span class="{ok}">{escape(a.status)}</span>'
                   f'<div class="muted">Último deploy: {escape(a.last_deploy or "—")} ({escape(a.last_deploy_status or "—")})</div></div>')
    for p in view.previews:
        out.append(f'<div class="card">🔎 Preview {_a(p["url"], f"{p["repo"]} PR #{p["number"]}")}</div>')
    # 4. Salud y consumo
    out.append("<h2>🩺 Salud y consumo</h2>")
    out.append(_err(view, "salud"))
    out.append('<div class="card"><table>' + "".join(
        f'<tr><td>{escape(c.name)}</td><td class="{"ok" if c.ok else "bad"}">{"OK" if c.ok else "FALLA"}</td>'
        f'<td class="muted">{escape(c.detail)}</td></tr>' for c in view.health) + "</table></div>")
    if view.usage:
        out.append('<div class="card"><table><tr><td></td><td class="muted">24 h</td><td class="muted">7 días</td></tr>' + "".join(
            f'<tr><td>{escape(u["engine"])}</td><td>{u["tasks_24h"]} tareas · {u["minutes_24h"]:.0f} min</td>'
            f'<td>{u["tasks_7d"]} tareas · {u["minutes_7d"]:.0f} min</td></tr>' for u in view.usage) + "</table></div>")
    else:
        out.append('<p class="muted">Sin tareas en los últimos 7 días.</p>')
    # 5. Resumen del operador (a pedido)
    out.append(render_summary(view.summary, view.errors.get("resumen"), view.updated))
    out.append("</body></html>")
    return "".join(out)
