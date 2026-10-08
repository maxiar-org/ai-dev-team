# Fase 4d: vista de estado (plan de implementación)

> **Para agentes que ejecuten este plan:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementarlo tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguir el avance.

**Objetivo:** el servicio `estado`, que publica en `estado.maxiar.dev` un HTML pensado para el celular con: qué espera a Eduardo (con el orden de merge), el trabajo en curso, los despliegues y previews, y la salud y el consumo.

**Arquitectura:** `python -m dispatcher.estado`, con la misma imagen del dispatcher.
- Un **recolector** (I/O) arma un `Snapshot` cada 60 s.
- **`build_view`** y **`render`** son funciones puras con tests.
- Un servidor HTTP de la librería estándar devuelve el último HTML.
- Si una fuente falla, el error queda registrado solo en su sección.

**Stack:** Python 3.12 (stdlib `http.server` y `html`), httpx, pytest y respx. API de GitHub (con el token del bot) y API de Coolify.

**Spec:** `docs/superpowers/specs/2026-10-08-fase-4d-vista-de-estado-design.md`

## Restricciones globales

- Solo lectura: nada de cambios en GitHub ni en Coolify.
- Cero LLM.
- Todo el texto externo pasa por `html.escape`.
- Todo corre en Docker (servicio `estado` del compose) y se publica solo por el túnel, detrás de Access.
- Un error en una fuente nunca tira la página.

## Foco de revisión

1. **Títulos de issues o PRs con HTML** (`<script>`): tienen que mostrarse escapados. Test: `test_render_escapes_external_text` (tarea 3).
2. **Coolify o GitHub caídos:** la sección afectada muestra "sin datos" y el resto se arma igual. Test: `test_collector_isolates_source_errors` (tarea 4).
3. **Dependencias en ciclo entre PRs que esperan a Eduardo:** el orden no entra en un bucle infinito. Test: `test_merge_order_survives_dependency_cycle` (tarea 2).
4. **PR cerrado con una preview vieja en el historial de Coolify:** no se muestra ese link. Test: `test_preview_link_only_for_open_prs_with_deploy` (tarea 2).
5. **`metrics.csv` vacío o inexistente:** la sección de consumo muestra 0, sin error. Test: `test_usage_handles_empty_metrics` (tarea 2).

---

### Tarea 1: Clientes (GitHub y Coolify)

**Archivos:**
- Crear: `dispatcher/src/dispatcher/coolify.py`
- Modificar: `dispatcher/src/dispatcher/github.py`
- Tests: `dispatcher/tests/test_coolify.py`, `dispatcher/tests/test_github.py`

**Interfaces:**
- Produce:
  - `GitHubClient.pr_details(repo, number) -> dict`, con las claves `head_sha`, `head_ref`, `mergeable_state`, `files` (tupla) y `ci` (`success`, `failure`, `pending` o `none`). El CI se toma de `actions/runs?head_sha=`.
  - `GitHubClient.last_comment_by(repo, number, login) -> str | None`
  - `CoolifyClient(base_url, token, http=None)`, con el método `.apps() -> list[AppInfo]`.
  - `AppInfo` se define en `view.py` (tarea 2), pero el cliente lo construye. Por eso en esta tarea se crea `view.py` solo con `AppInfo`, y la tarea 2 lo completa.

- [ ] **Paso 1: Tests que fallan.**

`dispatcher/tests/test_coolify.py`:

```python
import respx

from dispatcher.coolify import CoolifyClient

B = "http://coolify:8080/api/v1"


@respx.mock
def test_apps_with_last_deploy_and_previews():
    respx.get(f"{B}/applications").respond(json=[
        {"uuid": "u1", "name": "qr-generator", "git_repository": "maxiar-org/qr-generator", "fqdn": "http://qr.maxiar.dev",
         "status": "running:healthy", "preview_url_template": "qr-pr-{{pr_id}}.maxiar.dev"},
        {"uuid": "u2", "name": "preview-lab", "git_repository": "maxiar-org/preview-lab", "fqdn": None,
         "docker_compose_domains": '{"app":{"domain":"http://preview-lab.maxiar.dev"}}', "status": "running:unknown",
         "preview_url_template": None},
    ])
    respx.get(f"{B}/deployments/applications/u1").respond(json={"deployments": [
        {"pull_request_id": 23, "status": "finished", "created_at": "2026-10-08T05:00:00Z"},
        {"pull_request_id": 0, "status": "finished", "created_at": "2026-10-08T04:57:00Z"},
    ]})
    respx.get(f"{B}/deployments/applications/u2").respond(json={"deployments": []})
    apps = {a.name: a for a in CoolifyClient("http://coolify:8080/api/v1", "t").apps()}
    qr = apps["qr-generator"]
    assert (qr.repo, qr.url, qr.status) == ("maxiar-org/qr-generator", "https://qr.maxiar.dev", "running:healthy")
    assert (qr.last_deploy, qr.last_deploy_status, qr.preview_prs) == ("2026-10-08T04:57:00Z", "finished", (23,))
    assert apps["preview-lab"].url == "https://preview-lab.maxiar.dev"
```

Agregar a `dispatcher/tests/test_github.py`:

```python
@respx.mock
def test_pr_details_and_last_comment(gh):
    route("GET", "/pulls/7").respond(json={"head": {"sha": "abc", "ref": "agent/3-x"}, "mergeable_state": "clean"})
    route("GET", "/pulls/7/files").respond(json=[{"filename": "lib/a.dart"}, {"filename": "README.md"}])
    route("GET", "/actions/runs").respond(json={"workflow_runs": [{"status": "completed", "conclusion": "success"}]})
    route("GET", "/issues/9/comments").respond(json=[
        {"user": {"login": "maxiar-ai-dev-team-bot"}, "body": "primero"},
        {"user": {"login": "maxiar"}, "body": "humano"},
        {"user": {"login": "maxiar-ai-dev-team-bot"}, "body": "último del bot"},
    ])
    d = gh.pr_details("qr", 7)
    assert d == {"head_sha": "abc", "head_ref": "agent/3-x", "mergeable_state": "clean", "files": ("lib/a.dart", "README.md"), "ci": "success"}
    assert gh.last_comment_by("qr", 9, "maxiar-ai-dev-team-bot") == "último del bot"
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q tests/test_coolify.py tests/test_github.py`. Resultado esperado: FAIL.

- [ ] **Paso 3: Implementar.**

  **`github.py`:** agregar a `GitHubClient`:

```python
    def pr_details(self, repo: str, number: int) -> dict:
        resp = self.http.get(f"{self._repo(repo)}/pulls/{number}")
        resp.raise_for_status()
        pr = resp.json()
        sha = pr["head"]["sha"]
        files = tuple(f["filename"] for f in self._paginate(f"{self._repo(repo)}/pulls/{number}/files", {"per_page": 100}))
        runs = self.http.get(f"{self._repo(repo)}/actions/runs", params={"head_sha": sha, "per_page": 20})
        runs.raise_for_status()
        wr = runs.json().get("workflow_runs", [])
        if not wr:
            ci = "none"
        elif any(r.get("conclusion") in ("failure", "cancelled", "timed_out") for r in wr):
            ci = "failure"
        elif any(r.get("status") != "completed" for r in wr):
            ci = "pending"
        else:
            ci = "success"
        return {"head_sha": sha, "head_ref": pr["head"]["ref"], "mergeable_state": pr.get("mergeable_state"),
                "files": files, "ci": ci}

    def last_comment_by(self, repo: str, number: int, login: str) -> str | None:
        comments = self._paginate(f"{self._repo(repo)}/issues/{number}/comments", {"per_page": 100})
        mine = [c.get("body") or "" for c in comments if (c.get("user") or {}).get("login") == login]
        return mine[-1] if mine else None
```

  **`view.py`** (inicial; se completa en la tarea 2):

```python
"""Vista de estado del AI Dev Team. Funciones puras: build_view(Snapshot) -> View y render(View) -> HTML."""

from __future__ import annotations

from dataclasses import dataclass


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
```

  **`coolify.py`:**

```python
"""Cliente mínimo de la API de Coolify (solo lectura) para la vista de estado."""

from __future__ import annotations

import json

import httpx

from .view import AppInfo


def _https(url: str) -> str:
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


class CoolifyClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=base_url, timeout=20,
                                         headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def apps(self) -> list[AppInfo]:
        resp = self.http.get("/applications")
        resp.raise_for_status()
        out = []
        for a in resp.json():
            url = (a.get("fqdn") or "").split(",")[0]
            if not url and a.get("docker_compose_domains"):
                domains = json.loads(a["docker_compose_domains"]) if isinstance(a["docker_compose_domains"], str) else a["docker_compose_domains"]
                url = next((d.get("domain", "") for d in domains.values() if d.get("domain")), "")
            deps = self.http.get(f"/deployments/applications/{a['uuid']}", params={"take": 30})
            deps.raise_for_status()
            body = deps.json()
            items = body.get("deployments", body) if isinstance(body, dict) else body
            main = next((d for d in items if not d.get("pull_request_id")), None)
            previews = sorted({int(d["pull_request_id"]) for d in items if d.get("pull_request_id") and d.get("status") == "finished"})
            out.append(AppInfo(
                name=a.get("name", ""), repo=a.get("git_repository", ""), url=_https(url), status=a.get("status", ""),
                last_deploy=main.get("created_at") if main else None, last_deploy_status=main.get("status") if main else None,
                preview_template=a.get("preview_url_template"), preview_prs=tuple(previews),
            ))
        return out
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.
- [ ] **Paso 5:** commit con el mensaje `feat(estado): clientes de GitHub (detalle de PR) y Coolify`.

---

### Tarea 2: `build_view` (lógica pura)

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/view.py`
- Test: `dispatcher/tests/test_view.py`

**Interfaces:**
- Produce:
  - `PRInfo(repo, number, title, url, labels, body="", head_ref="", mergeable_state=None, ci="none", files=())`
  - `Snapshot` (campos de la sección 4 del spec)
  - `View`
  - `build_view(snap) -> View`
  - Helpers: `issue_of(pr) -> int | None` y `merge_order(waiting, issues) -> list[PRInfo]`

- [ ] **Paso 1: Tests que fallan.** Crear `dispatcher/tests/test_view.py`:

```python
from datetime import date

from dispatcher.models import Item
from dispatcher.view import AppInfo, PRInfo, Snapshot, build_view, merge_order
from dispatcher.watchdog import Check

NOW = 1_791_500_000.0  # 2026-10-08 aprox.


def pr(n, *labels, body="", ref=None, clean=True, ci="success", files=()):
    return PRInfo("qr", n, f"PR {n}", f"https://github.com/o/qr/pull/{n}", frozenset(labels), body,
                  ref or f"agent/{n}-x", "clean" if clean else "dirty", ci, tuple(files))


def issue(n, *labels, body=""):
    return Item("qr", n, "issue", f"Issue {n}", body, frozenset(labels))


def test_waiting_prs_exclude_agent_labels_and_needs_human():
    snap = Snapshot(now=NOW, prs=[pr(10), pr(11, "agent:review"), pr(12, "agent:working"), pr(13, "needs:human")])
    assert [w["number"] for w in build_view(snap).waiting] == [10]


def test_merge_order_clean_green_first_then_dependencies_then_number():
    a = pr(20, body="Closes #5")             # issue 5 depende de 4
    b = pr(21, body="Closes #4")
    c = pr(22, clean=False, body="Closes #6")
    issues = [issue(5, body="Depende de #4"), issue(4), issue(6)]
    assert [p.number for p in merge_order([a, b, c], issues)] == [21, 20, 22]


def test_merge_order_survives_dependency_cycle():
    a = pr(30, body="Closes #7")
    b = pr(31, body="Closes #8")
    issues = [issue(7, body="Depende de #8"), issue(8, body="Depende de #7")]
    assert sorted(p.number for p in merge_order([a, b], issues)) == [30, 31]


def test_overlapping_files_warn_on_later_pr():
    snap = Snapshot(now=NOW, prs=[pr(10, files=("lib/home.dart",)), pr(11, files=("lib/home.dart", "x"))])
    w = {x["number"]: x for x in build_view(snap).waiting}
    assert w[10]["warnings"] == [] and "conflicto con #10" in w[11]["warnings"][0]


def test_preview_link_only_for_open_prs_with_deploy():
    app = AppInfo("qr-generator", "maxiar-org/qr", "https://qr.maxiar.dev", "running", preview_template="qr-pr-{{pr_id}}.maxiar.dev",
                  preview_prs=(10, 99))
    snap = Snapshot(now=NOW, prs=[pr(10), pr(11)], apps=[app], org="maxiar-org")
    w = {x["number"]: x for x in build_view(snap).waiting}
    assert w[10]["preview"] == "https://qr-pr-10.maxiar.dev" and w[11]["preview"] is None
    assert build_view(snap).previews == [{"repo": "qr", "number": 10, "url": "https://qr-pr-10.maxiar.dev"}]


def test_needs_human_alerts_and_tokens():
    snap = Snapshot(now=NOW, issues=[issue(8, "needs:human")], human_notes={"qr#8": "¿Qué medida usa?"},
                    ops=[(3, "[ops] canvas", "https://x/3")],
                    expiries={"GITHUB_TOKEN": date(2026, 10, 30), "CLAUDE_CODE_OAUTH_TOKEN": date(2027, 10, 4)})
    v = build_view(snap)
    assert v.human == [{"repo": "qr", "number": 8, "title": "Issue 8", "url": "https://github.com/maxiar-org/qr/issues/8", "note": "¿Qué medida usa?"}]
    assert v.alerts == [{"title": "[ops] canvas", "url": "https://x/3"}]
    assert len(v.tokens) == 1 and "GITHUB_TOKEN" in v.tokens[0]


def test_work_stages():
    snap = Snapshot(now=NOW, org="maxiar-org",
                    issues=[issue(1, "agent:dev", body="Depende de #2"), issue(2, "agent:working"), issue(3, "agent:dev"), issue(4)],
                    prs=[pr(9, "agent:qa")],
                    active={"qr#2": {"role": "dev", "engine": "codex", "started_at": NOW - 600}})
    st = {w["number"]: w["stage"] for w in build_view(snap).work["qr"]}
    assert st[1] == "bloqueado (depende de #2)" and st[2] == "dev · codex · hace 10 min"
    assert st[3] == "listo para agentes" and st[4] == "backlog" and st[9] == "QA (en cola)"


def test_usage_handles_empty_metrics():
    assert build_view(Snapshot(now=NOW)).usage == []


def test_usage_counts_last_24h_and_7d():
    from datetime import datetime, timezone
    iso = lambda h: datetime.fromtimestamp(NOW - h * 3600, tz=timezone.utc).isoformat()
    rows = [{"motor": "codex", "inicio": iso(1), "duracion_min": "5.0"}, {"motor": "codex", "inicio": iso(48), "duracion_min": "3.0"},
            {"motor": "claude", "inicio": iso(200), "duracion_min": "9.0"}]
    u = {x["engine"]: x for x in build_view(Snapshot(now=NOW, metrics=rows)).usage}
    assert (u["codex"]["tasks_24h"], u["codex"]["tasks_7d"], u["codex"]["minutes_7d"]) == (1, 2, 8.0)
    assert "claude" not in u
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q tests/test_view.py`. Resultado esperado: FAIL.

- [ ] **Paso 3: Implementar** (completar `view.py`):

```python
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .decide import parse_dependencies
from .models import LABEL_DEV, LABEL_DOCS, LABEL_FIX, LABEL_HUMAN, LABEL_QA, LABEL_REVIEW, LABEL_WORKING, Item
from .watchdog import Check

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
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.
- [ ] **Paso 5:** commit con el mensaje `feat(estado): build_view con orden de merge, etapas, previews y consumo`.

---

### Tarea 3: `render` (HTML)

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/view.py` (agregar `render`)
- Test: `dispatcher/tests/test_view.py`

- [ ] **Paso 1: Tests que fallan:**

```python
from dispatcher.view import View, render


def test_render_sections_and_empty_state():
    html = render(View(updated=NOW))
    for title in ("Qué espera de ti", "Trabajo en curso", "Despliegues", "Salud y consumo", "Resumen del operador"):
        assert title in html
    assert "Nada pendiente" in html and 'http-equiv="refresh"' in html


def test_render_escapes_external_text():
    v = View(updated=NOW, waiting=[{"repo": "qr", "number": 1, "title": "<script>x</script>", "url": "https://g/1", "ci": "success",
                                    "clean": True, "preview": None, "issue": None, "warnings": []}])
    html = render(v)
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


def test_render_shows_source_errors():
    assert "sin datos" in render(View(updated=NOW, errors={"coolify": "ConnectError"}))
```

- [ ] **Paso 2:** ejecutar `uv run pytest -q tests/test_view.py`. Resultado esperado: FAIL.

- [ ] **Paso 3: Implementar.** Agregar a `view.py`:

```python
from html import escape

CSS = """
:root{color-scheme:dark}body{font:15px/1.45 -apple-system,system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:14px;max-width:760px;margin:auto}
h1{font-size:20px;margin:4px 0 2px}h2{font-size:16px;margin:22px 0 8px;border-bottom:1px solid #30363d;padding-bottom:4px}
.muted{color:#8b949e;font-size:13px}.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:10px 12px;margin:8px 0}
.urgent{border-color:#d29922}a{color:#58a6ff;text-decoration:none}.ok{color:#3fb950}.bad{color:#f85149}.warn{color:#d29922}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:4px 2px;border-bottom:1px solid #21262d;vertical-align:top}
.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;background:#21262d;margin-left:4px}
"""


def _a(url: str | None, text: str) -> str:
    return f'<a href="{escape(url or "#", quote=True)}">{escape(text)}</a>' if url else escape(text)


def _err(view: View, section: str) -> str:
    return f'<p class="bad">⚠️ sin datos ({escape(view.errors[section])})</p>' if section in view.errors else ""


def render(view: View) -> str:
    updated = datetime.fromtimestamp(view.updated, tz=timezone.utc).strftime("%H:%M:%S UTC")
    out = [f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta http-equiv="refresh" content="60"><title>Estado · AI Dev Team</title><style>{CSS}</style></head><body>',
           f'<h1>AI Dev Team</h1><div class="muted">Actualizado {updated} · se recarga cada minuto</div>']
    # 1. Qué espera de ti
    out.append("<h2>🔔 Qué espera de ti</h2>")
    out.append(_err(view, "github"))
    if not (view.waiting or view.human or view.alerts or view.tokens):
        out.append('<p class="ok">Nada pendiente 🎉</p>')
    for i, w in enumerate(view.waiting, 1):
        ci = {"success": '<span class="ok">CI ✓</span>', "failure": '<span class="bad">CI ✗</span>',
              "pending": '<span class="warn">CI …</span>'}.get(w["ci"], "")
        conflict = "" if w["clean"] else '<span class="warn">conflictos</span>'
        preview = f' · {_a(w["preview"], "preview")}' if w["preview"] else ""
        warns = "".join(f'<div class="warn">⚠️ {escape(x)}</div>' for x in w["warnings"])
        out.append(f'<div class="card urgent"><b>{i}.</b> {_a(w["url"], f"{w["repo"]} #{w["number"]}: {w["title"]}")}'
                   f'<div class="muted">Revisar y mergear · {ci} {conflict}{preview}</div>{warns}</div>')
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
    # 5. Reservado (opción C)
    out.append('<h2>🤖 Resumen del operador</h2><p class="muted">Próximamente: resumen narrativo a pedido.</p>')
    out.append("</body></html>")
    return "".join(out)
```

  Nota: las f-strings con comillas anidadas del mismo tipo requieren Python 3.12 o superior, que es la versión de la imagen. Localmente, `uv` usa 3.12 o superior.

- [ ] **Paso 4:** ejecutar `uv run pytest -q`. Resultado esperado: todo pasa.
- [ ] **Paso 5:** commit con el mensaje `feat(estado): render HTML para el celular`.

---

### Tarea 4: Recolector, servidor y compose

**Archivos:**
- Crear: `dispatcher/src/dispatcher/estado.py`
- Modificar: `docker-compose.yml`, `.env.example`, `README.md`, `operador/claude/CLAUDE.md`
- Test: `dispatcher/tests/test_estado.py`

- [ ] **Paso 1: Test que falla.** Crear `dispatcher/tests/test_estado.py`:

```python
from pathlib import Path

from dispatcher.estado import Collector
from dispatcher.models import Item


class GH:
    def list_open_items(self, repo):
        return [Item(repo, 1, "issue", "I", "", frozenset({"needs:human"})), Item(repo, 2, "pr", "P", "Closes #1", frozenset(), "agent/1-x")]

    def pr_details(self, repo, n):
        return {"head_sha": "s", "head_ref": "agent/1-x", "mergeable_state": "clean", "files": ("a",), "ci": "success"}

    def last_comment_by(self, repo, n, login):
        return "pregunta"

    def list_open_issue_titles(self, repo, label):
        return {"[ops] canvas": 5}


class BrokenCoolify:
    def apps(self):
        raise RuntimeError("coolify caído")


def test_collector_isolates_source_errors(tmp_path):
    c = Collector(GH(), BrokenCoolify(), repos=("qr",), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                  state_path=tmp_path / "no-existe.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={})
    snap = c.collect(now=1000.0)
    assert [p.number for p in snap.prs] == [2] and snap.human_notes == {"qr#1": "pregunta"}
    assert snap.ops == [(5, "[ops] canvas", "https://github.com/maxiar-org/ai-dev-team/issues/5")]
    assert "coolify" in snap.errors and snap.apps == [] and snap.active == {}
```

- [ ] **Paso 2:** ejecutar `uv run pytest -q tests/test_estado.py`. Resultado esperado: FAIL.

- [ ] **Paso 3: Implementar `estado.py`:**

```python
"""Servicio de la vista de estado: recolecta cada 60 s y sirve el HTML (python -m dispatcher.estado)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .coolify import CoolifyClient
from .github import GitHubClient
from .metrics import MetricsLog
from .models import LABEL_HUMAN
from .view import PRInfo, Snapshot, build_view, render
from .watchdog import parse_expiry, run_checks

log = logging.getLogger("estado")


class Collector:
    def __init__(self, github, coolify, repos, org, bot_login, ops_repo, state_path: Path, metrics_path: Path,
                 checker: Callable[[], list], expiries: dict):
        self.github, self.coolify, self.repos, self.org = github, coolify, repos, org
        self.bot_login, self.ops_repo = bot_login, ops_repo
        self.state_path, self.metrics_path, self.checker, self.expiries = state_path, metrics_path, checker, expiries

    def collect(self, now: float) -> Snapshot:
        snap = Snapshot(now=now, org=self.org, expiries=self.expiries)

        def section(name: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except Exception as exc:  # una fuente caída nunca tira la página
                log.warning("Sección %s sin datos: %s", name, exc)
                snap.errors[name] = f"{type(exc).__name__}: {exc}"[:200]

        def github() -> None:
            for repo in self.repos:
                for it in self.github.list_open_items(repo):
                    if it.kind == "pr":
                        d = self.github.pr_details(repo, it.number)
                        snap.prs.append(PRInfo(repo, it.number, it.title, f"https://github.com/{self.org}/{repo}/pull/{it.number}",
                                               it.labels, it.body, d["head_ref"], d["mergeable_state"], d["ci"], d["files"]))
                    else:
                        snap.issues.append(it)
                    if LABEL_HUMAN in it.labels:
                        note = self.github.last_comment_by(repo, it.number, self.bot_login)
                        if note:
                            snap.human_notes[f"{repo}#{it.number}"] = note
            titles = self.github.list_open_issue_titles(self.ops_repo, "ops")
            snap.ops = [(n, t, f"https://github.com/{self.org}/{self.ops_repo}/issues/{n}") for t, n in sorted(titles.items(), key=lambda x: x[1])]

        def dispatcher() -> None:
            if self.state_path.exists():
                snap.active = json.loads(self.state_path.read_text()).get("active", {})

        def coolify() -> None:
            if self.coolify is not None:
                snap.apps = self.coolify.apps()

        def salud() -> None:
            snap.checks = self.checker()
            snap.metrics = MetricsLog(self.metrics_path).read()

        section("github", github)
        section("dispatcher", dispatcher)
        section("coolify", coolify)
        section("salud", salud)
        return snap


class Page:
    def __init__(self) -> None:
        self.html = "<!doctype html><meta charset=utf-8><p>Cargando…</p>"


def serve(page: Page, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"ok" if self.path == "/health" else page.html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain" if self.path == "/health" else "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # sin ruido en los logs
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = os.environ
    org = env.get("GITHUB_ORG", "maxiar-org")
    github = GitHubClient(env["GITHUB_TOKEN"], org)
    coolify = CoolifyClient(env["COOLIFY_API_URL"], env["COOLIFY_API_TOKEN"]) if env.get("COOLIFY_API_TOKEN") else None
    checker = lambda: run_checks(  # noqa: E731
        env.get("CANVAS_URL", "http://canvas:8000"), env["CANVAS_API_KEY"], Path(env.get("HEARTBEAT_PATH", "/state/heartbeat")),
        env.get("TUNNEL_READY_URL", ""), "/", time.time(), coolify_health_url=env.get("COOLIFY_HEALTH_URL", ""))
    collector = Collector(
        github, coolify, tuple(r.strip() for r in env["REPOS"].split(",") if r.strip()), org,
        env.get("BOT_LOGIN", "maxiar-ai-dev-team-bot"), env.get("OPS_REPO", "ai-dev-team"),
        Path(env.get("STATE_PATH", "/state/state.json")), Path(env.get("METRICS_PATH", "/pilot/metrics.csv")), checker,
        {"GITHUB_TOKEN": parse_expiry(env.get("GITHUB_TOKEN_EXPIRES")),
         "CLAUDE_CODE_OAUTH_TOKEN": parse_expiry(env.get("CLAUDE_TOKEN_EXPIRES"))},
    )
    page = Page()
    interval = int(env.get("ESTADO_INTERVAL", "60"))

    def loop() -> None:
        while True:
            try:
                page.html = render(build_view(collector.collect(time.time())))
            except Exception:
                log.exception("No pude armar la vista")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    serve(page, int(env.get("ESTADO_PORT", "8090"))).serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Paso 4:** ejecutar `uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5: Compose.** Agregar el servicio:

```yaml
  estado:
    image: ai-dev-team-dispatcher
    pull_policy: never  # la construye el servicio dispatcher
    restart: unless-stopped
    depends_on:
      - dispatcher
    entrypoint: ["python", "-m", "dispatcher.estado"]
    networks: [default, coolify]
    environment:
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_ORG: ${GITHUB_ORG:-maxiar-org}
      REPOS: ${REPOS}
      BOT_LOGIN: ${BOT_LOGIN:-maxiar-ai-dev-team-bot}
      OPS_REPO: ai-dev-team
      CANVAS_URL: http://canvas:8000
      CANVAS_API_KEY: ${CANVAS_API_KEY}
      HEARTBEAT_PATH: /state/heartbeat
      STATE_PATH: /state/state.json
      METRICS_PATH: /pilot/metrics.csv
      TUNNEL_READY_URL: http://cloudflared:2000/ready
      COOLIFY_HEALTH_URL: ${COOLIFY_HEALTH_URL:-}
      COOLIFY_API_URL: http://coolify:8080/api/v1
      COOLIFY_API_TOKEN: ${COOLIFY_API_TOKEN:-}
      GITHUB_TOKEN_EXPIRES: ${GITHUB_TOKEN_EXPIRES:-}
      CLAUDE_TOKEN_EXPIRES: ${CLAUDE_TOKEN_EXPIRES:-}
    volumes:
      - dispatcher-state:/state:ro
      - ./pilot:/pilot:ro
```

  Agregar `COOLIFY_API_TOKEN=` en `.env.example`, con un comentario ("token de la API de Coolify, solo lectura para la vista de estado y para el operador").

- [ ] **Paso 6: Documentación.**
  - En el README, sección "Mini-PC y operador": agregar **Estado:** https://estado.maxiar.dev (Access), con lo que espera de ti, el trabajo en curso, los despliegues y la salud. Se actualiza cada minuto.
  - En `operador/claude/CLAUDE.md`, en Arquitectura: agregar `estado` (servicio de la vista `estado.maxiar.dev`, que usa la misma imagen del dispatcher).

- [ ] **Paso 7:** validar el compose (`docker compose config --quiet` con un `.env` de relleno) y hacer commit con el mensaje `feat(estado): servicio de la vista de estado en el compose`.

---

### Tarea 5: Despliegue y verificación

- [ ] **Paso 1:** mergear a `main` y publicar. En la mini-PC:
  - `git pull`;
  - `docker compose build dispatcher`;
  - `docker compose up -d --no-deps dispatcher watchdog estado` (antes, verificar que no haya tareas activas);
  - `curl -s http://127.0.0.1` no aplica (el servicio no publica puerto); verificar desde la red de Compose con `docker compose exec estado python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8090/').read()[:300])"`.
- [ ] **Paso 2 👤:** en Cloudflare, agregar al túnel la ruta `estado.maxiar.dev` → `HTTP` → `estado:8090`, **por encima** de `*.maxiar.dev`. Después crear la aplicación de Access **Estado** (`estado.maxiar.dev`) con la política de Eduardo.
- [ ] **Paso 3:** verificar que `curl https://estado.maxiar.dev` da 302 (Access), y que Eduardo la abre desde el celular y ve las cuatro secciones.
- [ ] **Paso 4:** prueba de resiliencia: `docker stop coolify` durante un ciclo, comprobar que "Despliegues" muestra "sin datos" y el resto sigue bien, y `docker start coolify`.
- [ ] **Paso 5:** registrar en la bitácora y actualizar la memoria del operador.
