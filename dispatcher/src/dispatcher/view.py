"""Vista de estado del AI Dev Team: build_view(Snapshot) -> View y render(View) -> HTML, ambas puras."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

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


def issue_of(pr: PRInfo) -> int | None:
    m = re.match(r"agent/(\d+)-", pr.head_ref or "")
    if m:
        return int(m.group(1))
    m = CLOSES_RE.search(pr.body or "")
    return int(m.group(1)) if m else None


def merge_order(waiting: list[PRInfo], issues: list[Item]) -> list[PRInfo]:
    by_issue = {issue_of(p): p for p in waiting if issue_of(p) is not None}
    bodies = {i.number: i.body for i in issues}
    base = sorted(waiting, key=lambda p: (0 if p.mergeable_state == "clean" and p.ci in ("success", "none") else 1, p.number))

    def blockers(p: PRInfo) -> set[int]:
        iss = issue_of(p)
        deps = parse_dependencies(bodies.get(iss, "")) if iss is not None else ()
        return {by_issue[d].number for d in deps if d in by_issue and by_issue[d] is not p}

    result: list[PRInfo] = []
    pending = list(base)
    while pending:
        done = {p.number for p in result}
        pick = next((p for p in pending if blockers(p) <= done), None)
        if pick is None:  # ciclo de dependencias: se respeta el orden base
            result.extend(pending)
            break
        result.append(pick)
        pending.remove(pick)
    return result


def _preview(pr: PRInfo, apps: list[AppInfo], org: str) -> str | None:
    for a in apps:
        if a.repo in (f"{org}/{pr.repo}", pr.repo) and a.preview_template and pr.number in a.preview_prs:
            return "https://" + a.preview_template.replace("{{pr_id}}", str(pr.number))
    return None


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
        except (KeyError, ValueError):
            continue
        if age > 7 * 86400:
            continue
        e = acc[r.get("motor", "?")]
        e["tasks_7d"] += 1
        e["minutes_7d"] += minutes
        if age <= 86400:
            e["tasks_24h"] += 1
            e["minutes_24h"] += minutes
    return [{"engine": k, **v} for k, v in sorted(acc.items())]


def build_view(snap: Snapshot) -> View:
    v = View(updated=snap.now, apps=snap.apps, health=snap.checks, errors=dict(snap.errors))
    waiting = [p for p in snap.prs if not (p.labels & AGENT_LABELS) and LABEL_HUMAN not in p.labels]
    ordered = merge_order(waiting, snap.issues)
    seen_files: list[tuple[int, set[str]]] = []
    for p in ordered:
        warnings = [f"puede generar conflicto con #{n} (tocan {', '.join(sorted(f & set(p.files)))})"
                    for n, f in seen_files if f & set(p.files)]
        seen_files.append((p.number, set(p.files)))
        v.waiting.append({"repo": p.repo, "number": p.number, "title": p.title, "url": p.url, "ci": p.ci,
                          "clean": p.mergeable_state == "clean", "preview": _preview(p, snap.apps, snap.org),
                          "issue": issue_of(p), "warnings": warnings})
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
            if (repo, n) in open_prs and a.preview_template:
                v.previews.append({"repo": repo, "number": n, "url": "https://" + a.preview_template.replace("{{pr_id}}", str(n))})
    v.usage = _usage(snap.metrics, snap.now)
    return v
