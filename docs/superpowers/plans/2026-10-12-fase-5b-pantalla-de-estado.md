# Fase 5b: pantalla de estado nueva, plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la página de `estado.maxiar.dev` por el tablero aprobado en Claude Design: te esperan, equipo por puesto, proyectos, despliegues y credenciales, consumo y presupuesto (7 y 30 días) y resumen.

**Architecture:** Se mantiene el servicio `estado` (Python, sin framework): `Collector` → `Snapshot` → `build_view` (puro) → `render` (puro) → HTML cacheado en `Page`. Los datos nuevos salen de `state.json`, `metrics.csv`, `limits.csv` y la API de GitHub. El HTML y los gráficos pasan a `render.py` y `charts.py`; el rango va por `?rango=`, y `/api/estado` devuelve la `View` como JSON.

**Tech Stack:** Python 3.12, `http.server`, `httpx`, pytest con respx, HTML y CSS sin dependencias de frontend.

**Spec:** `docs/superpowers/specs/2026-10-12-fase-5b-pantalla-de-estado-design.md`. Diseño: https://claude.ai/artifact/RrUtD84BVcAAbyqCEAuL4r

## Global Constraints

- Sin framework de frontend ni build. El único JS es el de recarga, y la página funciona sin él.
- Sin emojis en el HTML de la página: íconos SVG en línea con texto al lado.
- Colores de puesto fijos por motor: claro Gemini `#2a78d6`, Claude `#eb6834`, Codex `#1baf7a`; oscuro `#3987e5`, `#d95926`, `#199e70`.
- Superficies: claro `#f3f2ee` / `#fcfcfb`, tinta `#0b0b0b`, secundaria `#52514e`; oscuro `#121211` / `#1a1a19`, `#ffffff`, `#c3c2b7`.
- Estados: bien `#0ca30c`, advertencia `#fab219`, serio `#ec835a` (sin cupo, con rayado), crítico `#d03b3b`. Siempre con ícono y texto.
- Todo texto que viene de GitHub, Coolify o los CSV sale escapado con `html.escape`.
- Una fuente caída deja sin datos solo su sección ("sin datos (…)").
- Horas para Eduardo en `ESTADO_TZ` (por defecto `America/Argentina/Buenos_Aires`).
- Búsquedas de GitHub para presupuesto: como mucho una vez cada 600 s.
- Tests: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`. Hoy pasan 298.
- Commits con `git -c user.email=eduardo.jimenez@falconsoft.cl commit`, mensaje en español, terminando en `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Filas de `metrics.csv` incompletas (el dispatcher escribiendo) o de antes de la fase 5a (sin `puesto`, sin `fin`): la página no se cae y esas filas no cuentan. Test en la tarea 3 (`test_clean_metrics_drops_broken_rows`).
2. Un puesto en `slot_exhausted_until` con la hora ya vencida: se muestra libre, no "sin cupo hasta" una hora pasada. Test en la tarea 4 (`test_expired_exhaustion_is_free`).
3. GitHub de búsqueda caído después de una búsqueda buena: se siguen mostrando los datos cacheados y la sección avisa el error. Test en la tarea 7 (`test_period_cache_survives_search_error`).
4. `?rango=` con cualquier otro valor: responde el rango de 7 días, sin error. Test en la tarea 7 (`test_unknown_rango_falls_back_to_7`).
5. Sin `SLOTS` ni costos configurados (el compose de un proyecto nuevo): la sección de equipo usa los puestos por defecto y el costo da USD 0, sin división por cero. Test en la tarea 4 (`test_budget_without_costs_or_closed_issues`).

---

### Task 1: lectura compartida de puestos, costos y etiquetas

**Files:**
- Modify: `dispatcher/src/dispatcher/config.py:110-129`
- Test: `dispatcher/tests/test_config.py`

**Interfaces:**
- Produces: `parse_slots(env: Mapping[str, str]) -> tuple[Slot, ...]`, `parse_slot_costs(env, slots) -> dict[str, float]`, `parse_slot_labels(env, slots) -> dict[str, str]`, todas en `dispatcher.config`.

- [ ] **Step 1: Write the failing test**

Agregar al final de `dispatcher/tests/test_config.py`:

```python
from dispatcher.config import parse_slot_costs, parse_slot_labels, parse_slots
from dispatcher.models import Slot


def test_slot_parsers_are_shared_with_estado():
    env = {"SLOTS": "claude-senior:claude:senior,gemini:gemini:senior", "SLOT_COST_CLAUDE_SENIOR": "100",
           "SLOT_LABEL_CLAUDE_SENIOR": "Claude Max 5x · arquitectura"}
    slots = parse_slots(env)
    assert slots == (Slot("claude-senior", "claude", "senior"), Slot("gemini", "gemini", "senior"))
    assert parse_slot_costs(env, slots) == {"claude-senior": 100.0}
    assert parse_slot_labels(env, slots) == {"claude-senior": "Claude Max 5x · arquitectura"}
    assert parse_slots({}) == (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_config.py`
Expected: FAIL con `ImportError: cannot import name 'parse_slot_costs'`.

- [ ] **Step 3: Write minimal implementation**

En `config.py`, antes de `class ConfigError`, mover la lógica a funciones de módulo (el `ConfigError` se define antes; mover estas funciones debajo de `class ConfigError`):

```python
def _slot_env(name: str) -> str:
    return name.upper().replace("-", "_")


def parse_slots(env: Mapping[str, str]) -> tuple[Slot, ...]:
    raw = env.get("SLOTS", "").strip()
    if not raw:
        return DEFAULT_SLOTS
    slots: list[Slot] = []
    for part in (p.strip() for p in raw.split(",") if p.strip()):
        bits = part.split(":")
        if len(bits) != 3 or bits[1] not in ENGINES or not bits[0]:
            raise ConfigError(f"SLOTS: cada puesto es nombre:motor:nivel con motor en {ENGINES}, no {part!r}")
        slots.append(Slot(*bits))
    if len({s.name for s in slots}) != len(slots):
        raise ConfigError("SLOTS tiene nombres de puesto repetidos")
    return tuple(slots)


def parse_slot_costs(env: Mapping[str, str], slots: tuple[Slot, ...]) -> dict[str, float]:
    costs: dict[str, float] = {}
    for s in slots:
        raw = env.get(f"SLOT_COST_{_slot_env(s.name)}", "").strip()
        if raw:
            costs[s.name] = float(raw)
    return costs


def parse_slot_labels(env: Mapping[str, str], slots: tuple[Slot, ...]) -> dict[str, str]:
    """Línea de plan y rol bajo el nombre del puesto en la pantalla de estado (SLOT_LABEL_<PUESTO>)."""
    return {s.name: v for s in slots if (v := env.get(f"SLOT_LABEL_{_slot_env(s.name)}", "").strip())}
```

Y en `Config.from_env`, reemplazar la función interna `parse_slots` y el bucle de costos por:

```python
        slots = parse_slots(env)
        costs = parse_slot_costs(env, slots)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_config.py`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/config.py dispatcher/tests/test_config.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "refactor(config): lectura de puestos compartida con la vista de estado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: datos nuevos de GitHub (antigüedad, épicas, fechas de PR)

**Files:**
- Modify: `dispatcher/src/dispatcher/models.py` (`Item`, `CLOSES_RE`)
- Modify: `dispatcher/src/dispatcher/github.py` (`list_open_items`, `search_since`)
- Modify: `dispatcher/src/dispatcher/view.py` (`PRInfo.updated_at`, `CLOSES_RE` importado de models)
- Modify: `dispatcher/src/dispatcher/estado.py` (`_collect_repo` pasa `updated_at`)
- Test: `dispatcher/tests/test_github.py`

**Interfaces:**
- Produces: `Item.updated_at: str = ""`, `Item.sub_issues: tuple[int, int] | None = None` (completados, total); `PRInfo.updated_at: str = ""` (último campo); `models.CLOSES_RE`; `search_since` devuelve además `created_at`, `merged_at`, `closes: int | None` y `labels: list[str]`.

- [ ] **Step 1: Write the failing tests**

En `tests/test_github.py`, reemplazar `test_search_since_returns_compact_items` por:

```python
@respx.mock
def test_search_since_returns_compact_items(gh):
    r = respx.get("https://api.github.com/search/issues").respond(json={"items": [
        {"number": 23, "title": "Kit QR", "html_url": "https://github.com/maxiar-org/qr-generator/pull/23",
         "repository_url": "https://api.github.com/repos/maxiar-org/qr-generator", "closed_at": "2026-10-08T05:30:00Z",
         "created_at": "2026-10-08T01:00:00Z", "state": "closed", "body": "Closes #7",
         "labels": [{"name": "engine:codex"}], "pull_request": {"merged_at": "2026-10-08T05:30:00Z"}},
    ]})
    items = gh.search_since("org:maxiar-org is:pr is:merged merged:>=2026-10-08T00:00:00Z")
    assert items == [{"repo": "qr-generator", "number": 23, "title": "Kit QR",
                      "url": "https://github.com/maxiar-org/qr-generator/pull/23", "closed_at": "2026-10-08T05:30:00Z",
                      "state": "closed", "created_at": "2026-10-08T01:00:00Z", "merged_at": "2026-10-08T05:30:00Z",
                      "closes": 7, "labels": ["engine:codex"]}]
    assert r.calls.last.request.url.params["q"].startswith("org:maxiar-org is:pr")
```

Y agregar:

```python
@respx.mock
def test_list_open_items_reads_updated_at_and_sub_issues(gh):
    route("GET", "/pulls").respond(json=[])
    route("GET", "/issues").respond(json=[
        {"number": 11, "title": "Épica", "body": "", "labels": [{"name": "epic"}], "updated_at": "2026-10-12T05:00:00Z",
         "sub_issues_summary": {"total": 9, "completed": 4, "percent_completed": 44}},
        {"number": 12, "title": "Suelto", "body": "", "labels": [], "sub_issues_summary": {"total": 0, "completed": 0}},
    ])
    a, b = gh.list_open_items("qr")
    assert (a.updated_at, a.sub_issues) == ("2026-10-12T05:00:00Z", (4, 9))
    assert (b.updated_at, b.sub_issues) == ("", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_github.py`
Expected: FAIL en los dos tests (claves de más y `AttributeError: 'Item' object has no attribute 'updated_at'`).

- [ ] **Step 3: Write minimal implementation**

`models.py`: agregar `import re` arriba, y junto a las constantes de labels:

```python
CLOSES_RE = re.compile(r"(?i)\b(?:closes|fixes|resolves|cierra)\s+#(\d+)\b")
```

En `class Item`, después de `draft`:

```python
    updated_at: str = ""  # ISO de GitHub: la antigüedad en la pantalla de estado
    sub_issues: tuple[int, int] | None = None  # épicas: (completados, total) de sub_issues_summary
```

`view.py`: borrar la línea `CLOSES_RE = re.compile(...)` e importarlo: `from .models import CLOSES_RE, LABEL_DEV, ...`. En `PRInfo`, después de `files`:

```python
    updated_at: str = ""
```

`github.py`: importar `from .models import CLOSES_RE` (sumarlo al import existente de models). En `list_open_items`, en el `Item(...)`:

```python
                    draft=raw["number"] in drafts,
                    updated_at=raw.get("updated_at") or "",
                    sub_issues=_sub_issues(raw.get("sub_issues_summary")),
```

y a nivel de módulo:

```python
def _sub_issues(summary: dict | None) -> tuple[int, int] | None:
    total = (summary or {}).get("total") or 0
    return (int(summary.get("completed") or 0), int(total)) if total else None
```

`search_since`:

```python
    def search_since(self, query: str) -> list[dict]:
        resp = self.http.get("/search/issues", params={"q": query, "per_page": 100})
        resp.raise_for_status()
        out = []
        for i in resp.json().get("items", []):
            closes = CLOSES_RE.search(i.get("body") or "")
            out.append({"repo": i["repository_url"].rsplit("/", 1)[-1], "number": i["number"], "title": i["title"],
                        "url": i["html_url"], "closed_at": i.get("closed_at"), "state": i.get("state"),
                        "created_at": i.get("created_at"), "merged_at": (i.get("pull_request") or {}).get("merged_at"),
                        "closes": int(closes.group(1)) if closes else None,
                        "labels": [label["name"] for label in i.get("labels") or []]})
        return out
```

`estado.py`, en `_collect_repo`, pasar la antigüedad a los dos `PRInfo(...)`:

```python
                    prs.append(PRInfo(repo, it.number, it.title, url, it.labels, it.body, d["head_ref"],
                                      d["mergeable_state"], d["ci"], d["files"], it.updated_at))
                else:
                    prs.append(PRInfo(repo, it.number, it.title, url, it.labels, it.body, it.head_ref or "",
                                      updated_at=it.updated_at))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`
Expected: PASS (300 tests).

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/models.py dispatcher/src/dispatcher/github.py dispatcher/src/dispatcher/view.py dispatcher/src/dispatcher/estado.py dispatcher/tests/test_github.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(github): antigüedad, avance de épicas y fechas de PR para la vista de estado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: agregaciones nuevas (franja de 24 h, horas por día, tiempos de flujo)

**Files:**
- Modify: `dispatcher/src/dispatcher/team_report.py`
- Test: `dispatcher/tests/test_team_report.py`

**Interfaces:**
- Consumes: `metrics.iso`, `SlotStats`, `_ts`, `_rework` (ya existen).
- Produces:
  - `clean_metrics(rows) -> list[dict]` y `clean_limits(rows) -> list[dict]`: descartan filas que no se pueden leer;
  - `rework_per_issue(rows) -> float`;
  - `hour_strip(metrics_rows, limit_rows, slot: str, now: float, active_since: float | None = None, exhausted_until: float | None = None) -> list[str]`: 24 estados `"trabajando" | "sin_cupo" | "libre"`, el índice 0 es la hora que empieza hace 24 h;
  - `daily_hours(metrics_rows, slot_names: list[str], now: float, days: int, tz: ZoneInfo) -> list[dict]`: `[{"date": date, "minutes": {slot: float}}]`, del más viejo al de hoy;
  - `flow_times(merged: list[dict], metrics_rows, now: float, window_s: float) -> dict[str, float | None]`: segundos, con claves `issue_to_pr`, `pr_to_merge` y `total`.

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/test_team_report.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from dispatcher.team_report import clean_limits, clean_metrics, daily_hours, flow_times, hour_strip, rework_per_issue

HOUR = 3600.0


def mf(slot, start, end, rol="dev", numero=1, resultado="pr_abierto", repo="nikito", tipo="issue"):
    return {"repo": repo, "numero": str(numero), "rol": rol, "tipo": tipo, "puesto": slot, "inicio": iso(start),
            "fin": iso(end), "duracion_min": str((end - start) / 60), "resultado": resultado}


def test_clean_metrics_drops_broken_rows():
    good = mf("codex-senior", NOW - HOUR, NOW - 1800)
    rows = [good, {"repo": "x", "numero": "1", "rol": "dev", "inicio": None}, {"inicio": iso(NOW)},
            {**good, "duracion_min": "no"}]
    assert clean_metrics(rows) == [good]
    assert clean_limits([{"puesto": "a", "detectado": "x", "hasta": iso(NOW)}, lim("a", NOW, 1)]) == [lim("a", NOW, 1)]


def test_hour_strip_marks_work_over_exhaustion_and_counts_active_task():
    rows = [mf("codex-senior", NOW - 23.5 * HOUR, NOW - 23.2 * HOUR)]          # hora 0
    limits = [lim("codex-senior", NOW - 23.4 * HOUR, 3)]                        # horas 0 a 3; la 0 trabajó
    cells = hour_strip(rows, limits, "codex-senior", NOW, active_since=NOW - 0.5 * HOUR)
    assert len(cells) == 24
    assert cells[0] == "trabajando" and cells[1:4] == ["sin_cupo"] * 3 and cells[4] == "libre"
    assert cells[23] == "trabajando"
    assert hour_strip([], [], "codex-senior", NOW, exhausted_until=NOW + HOUR)[23] == "sin_cupo"
    assert hour_strip(rows, limits, "otro", NOW) == ["libre"] * 24


def test_daily_hours_by_local_day_and_slot():
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    rows = [mf("codex-senior", NOW - 600, NOW), mf("claude-senior", NOW - 3 * 86400, NOW - 3 * 86400 + 1800),
            mf("codex-senior", NOW - 40 * 86400, NOW - 40 * 86400 + 60)]
    days = daily_hours(rows, ["claude-senior", "codex-senior"], NOW, 7, tz)
    assert len(days) == 7 and days[-1]["date"] == datetime.fromtimestamp(NOW, tz).date()
    assert days[-1]["minutes"] == {"claude-senior": 0.0, "codex-senior": 10.0}
    assert days[-4]["minutes"]["claude-senior"] == 30.0
    assert sum(sum(d["minutes"].values()) for d in days) == 40.0
    assert len(daily_hours([], ["a"], NOW, 30, tz)) == 30


def test_flow_times_medians():
    rows = [mf("codex-senior", NOW - 10 * HOUR, NOW - 9 * HOUR, numero=1, resultado="error"),
            mf("codex-senior", NOW - 8 * HOUR, NOW - 7.5 * HOUR, numero=1),
            mf("codex-senior", NOW - 5 * HOUR, NOW - 4.5 * HOUR, numero=2)]
    merged = [{"repo": "nikito", "number": 10, "closes": 1, "created_at": iso(NOW - 7.5 * HOUR), "merged_at": iso(NOW - 2 * HOUR)},
              {"repo": "nikito", "number": 11, "closes": 2, "created_at": iso(NOW - 4.5 * HOUR), "merged_at": iso(NOW - HOUR)},
              {"repo": "nikito", "number": 12, "closes": None, "created_at": iso(NOW - 3 * HOUR), "merged_at": iso(NOW - HOUR)},
              {"repo": "nikito", "number": 9, "closes": 3, "created_at": iso(NOW - 40 * 86400), "merged_at": iso(NOW - 39 * 86400)}]
    f = flow_times(merged, rows, NOW, 7 * 86400)
    assert f["issue_to_pr"] == (2.5 * HOUR + 0.5 * HOUR) / 2      # issue 1: 10 h a 7,5 h; issue 2: 0,5 h
    assert f["pr_to_merge"] == 3.5 * HOUR                         # 5,5 h, 3,5 h y 2 h
    assert f["total"] == (8 * HOUR + 4 * HOUR) / 2
    assert flow_times([], [], NOW, DAY) == {"issue_to_pr": None, "pr_to_merge": None, "total": None}


def test_rework_per_issue_is_public():
    assert rework_per_issue([m("codex-senior", r, 1, NOW, 5) for r in ("dev", "fix", "qa")]) == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_team_report.py`
Expected: FAIL con `ImportError: cannot import name 'clean_limits'`.

- [ ] **Step 3: Write minimal implementation**

En `team_report.py`, cambiar los imports de arriba:

```python
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
```

y agregar al final:

```python
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
```

`_ts` ya existe arriba en el módulo (usa `datetime.fromisoformat`, que lee la `Z` de GitHub).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_team_report.py`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/team_report.py dispatcher/tests/test_team_report.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(consumo): franja de 24 h, horas por día y tiempos de flujo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: la `View` nueva (puestos, proyectos, credenciales y presupuesto)

**Files:**
- Modify: `dispatcher/src/dispatcher/view.py`
- Test: `dispatcher/tests/test_view.py`

**Interfaces:**
- Consumes: tareas 1 a 3 (`Item.sub_issues`, `PRInfo.updated_at`, `Item.updated_at`, `clean_metrics`, `clean_limits`, `hour_strip`, `daily_hours`, `flow_times`, `rework_per_issue`, `slot_stats`, `decision_alerts`).
- Produces (los consume `render.py` en la tarea 6):
  - `Snapshot` nuevos campos: `repos: tuple[str, ...] = ()`, `limits: list[dict]`, `slots: tuple[Slot, ...] = DEFAULT_SLOTS`, `slot_costs: dict[str, float]`, `slot_labels: dict[str, str]`, `exhausted: dict[str, float]`, `closed: list[dict]`, `merged: list[dict]`, `image_usd: float = 0.04`, `tz: str = "America/Argentina/Buenos_Aires"`.
  - `View` nuevos campos: `slots: list[dict]`, `projects: list[dict]`, `credentials: list[dict]`, `budget: dict[str, dict]` (claves `"7"` y `"30"`).
  - `v.waiting[i]["age"]` y `v.human[i]["age"]`: segundos o `None`; `v.human[i]["kind"]`: `"pr"` o `"issue"`.
  - Cada `v.slots[i]`: `{"name", "engine", "label", "status": "trabajando"|"libre"|"sin_cupo", "status_text", "detail", "cells": [{"state", "title"}], "tasks": int, "hours": float, "exhausted": float, "footer"}`.
  - Cada `v.projects[i]`: `{"repo", "epic": {"number", "title", "url", "done", "total"} | None, "counts": {columna: int}, "items": [filas de work]}` con `COLUMNS = ("Por hacer", "Dev", "Review", "QA", "Fix", "Te espera")`.
  - Cada `v.credentials[i]`: `{"name", "level": "ok"|"advertencia"|"critico", "text"}`.
  - `v.budget["7"]`: `{"days", "cost", "fixed", "images", "image_cost", "closed", "cost_per_issue", "rework", "cuts", "exhausted_hours", "daily", "exhausted", "flow", "alerts"}`; `daily` es la salida de `daily_hours`, `exhausted` es `[{"slot", "engine", "hours", "cuts"}]`.
  - `zone(name: str) -> ZoneInfo` (UTC si el nombre no existe).

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/test_view.py`:

```python
from datetime import datetime, timezone

from dispatcher.models import Slot
from dispatcher.view import COLUMNS

SLOTS3 = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))


def ts(h):
    return datetime.fromtimestamp(NOW - h * 3600, tz=timezone.utc).isoformat()


def row(slot, hours_ago, minutes, rol="dev", numero="1", imgs="0"):
    return {"repo": "qr", "numero": numero, "rol": rol, "tipo": "issue", "puesto": slot, "motor": slot.split("-")[0],
            "inicio": ts(hours_ago), "fin": ts(hours_ago - minutes / 60), "duracion_min": str(minutes),
            "resultado": "pr_abierto", "imagenes_gemini": imgs}


def test_slot_cards_working_free_and_out_of_quota():
    snap = Snapshot(now=NOW, slots=SLOTS3, tz="UTC",
                    active={"qr#6": {"role": "review", "engine": "claude", "slot": "claude-senior", "started_at": NOW - 120}},
                    exhausted={"gemini": NOW + 3 * 3600},
                    metrics=[row("codex-senior", 2, 30), row("gemini", 5, 10, imgs="3")],
                    slot_labels={"codex-senior": "Codex Pro · dev S/M"}, image_usd=0.04)
    cards = {c["name"]: c for c in build_view(snap).slots}
    assert [c["name"] for c in build_view(snap).slots] == ["claude-senior", "codex-senior", "gemini"]
    assert cards["claude-senior"]["status"] == "trabajando" and "review de qr #6 · hace 2 min" == cards["claude-senior"]["detail"]
    assert cards["codex-senior"]["status"] == "libre" and cards["codex-senior"]["label"] == "Codex Pro · dev S/M"
    assert cards["codex-senior"]["detail"].startswith("Terminó dev de qr #1 a las ")
    hhmm = datetime.fromtimestamp(NOW + 3 * 3600, tz=timezone.utc).strftime("%H:%M")
    assert cards["gemini"]["status"] == "sin_cupo" and cards["gemini"]["status_text"] == f"Sin cupo hasta {hhmm}"
    assert cards["codex-senior"]["tasks"] == 1 and cards["codex-senior"]["hours"] == 0.5
    assert len(cards["codex-senior"]["cells"]) == 24 and cards["codex-senior"]["cells"][21]["state"] == "trabajando"
    assert "3 imágenes" in cards["gemini"]["footer"] and "USD 0,12" in cards["gemini"]["footer"]
    assert cards["claude-senior"]["label"] == "claude · senior"


def test_expired_exhaustion_is_free():
    snap = Snapshot(now=NOW, slots=SLOTS3, exhausted={"gemini": NOW - 60})
    assert {c["name"]: c["status"] for c in build_view(snap).slots}["gemini"] == "libre"


def test_projects_group_stages_and_pick_current_epic():
    epic = Item("qr", 10, "issue", "Épica: Fase 0", "", frozenset({"epic"}))
    epic2 = Item("qr", 11, "issue", "Épica: Fase 1", "", frozenset({"epic"}), sub_issues=(4, 9))
    snap = Snapshot(now=NOW, repos=("qr", "lab"), issues=[epic, epic2, issue(1, "agent:dev"), issue(2, "needs:human"), issue(3)],
                    prs=[pr(9, "agent:qa"), pr(8)], active={"qr#5": {"role": "dev", "engine": "codex", "started_at": NOW}},
                    org="maxiar-org")
    snap.issues.append(issue(5, "agent:working"))
    p = {x["repo"]: x for x in build_view(snap).projects}
    assert list(p) == ["qr", "lab"]
    assert p["qr"]["epic"] == {"number": 11, "title": "Épica: Fase 1", "url": "https://github.com/maxiar-org/qr/issues/11", "done": 4, "total": 9}
    assert p["qr"]["counts"] == {"Por hacer": 2, "Dev": 1, "Review": 0, "QA": 1, "Fix": 0, "Te espera": 2}
    assert all(i["number"] not in (10, 11) for i in p["qr"]["items"])
    assert p["lab"] == {"repo": "lab", "epic": None, "counts": dict.fromkeys(COLUMNS, 0), "items": []}


def test_credentials_levels():
    snap = Snapshot(now=NOW, expiries={"A": date(2026, 10, 10), "B": date(2026, 10, 30), "C": date(2027, 10, 1),
                                       "D": date(2026, 10, 1), "E": None})
    levels = {c["name"]: c["level"] for c in build_view(snap).credentials}
    assert levels == {"A": "critico", "B": "advertencia", "C": "ok", "D": "critico"}


def test_budget_by_range():
    rows = [row("codex-senior", 2, 60, imgs="2"), row("codex-senior", 3, 30, rol="fix"), row("claude-senior", 10 * 24, 60)]
    limits = [{"puesto": "codex-senior", "detectado": ts(30), "hasta": ts(27)}]
    closed = [{"repo": "qr", "number": 1, "closed_at": ts(1), "labels": []},
              {"repo": "qr", "number": 10, "closed_at": ts(1), "labels": ["epic"]},
              {"repo": "qr", "number": 2, "closed_at": ts(20 * 24), "labels": []}]
    snap = Snapshot(now=NOW, slots=SLOTS3, metrics=rows, limits=limits, closed=closed,
                    slot_costs={"claude-senior": 100.0, "codex-senior": 200.0, "gemini": 20.0}, image_usd=0.04, tz="UTC")
    b7, b30 = build_view(snap).budget["7"], build_view(snap).budget["30"]
    assert b7["days"] == 7 and len(b7["daily"]) == 7 and len(b30["daily"]) == 30
    assert round(b7["fixed"], 2) == round(320 * 7 / 30, 2) and b7["images"] == 2 and round(b7["image_cost"], 2) == 0.08
    assert round(b7["cost"], 2) == round(320 * 7 / 30 + 0.08, 2)
    assert b7["closed"] == 1 and b30["closed"] == 2 and round(b7["cost_per_issue"], 2) == round(b7["cost"], 2)
    assert b7["rework"] == 1.0 and b7["cuts"] == 1 and b7["exhausted_hours"] == 3.0
    assert [e["slot"] for e in b7["exhausted"]] == ["claude-senior", "codex-senior", "gemini"]
    assert set(b7["flow"]) == {"issue_to_pr", "pr_to_merge", "total"}


def test_budget_without_costs_or_closed_issues():
    b = build_view(Snapshot(now=NOW)).budget["7"]
    assert b["cost"] == 0 and b["closed"] == 0 and b["cost_per_issue"] is None
    assert [e["slot"] for e in b["exhausted"]] == ["claude", "codex"]


def test_waiting_and_human_carry_age():
    p = PRInfo("qr", 10, "t", "u", frozenset(), "", "feat/x", "clean", "success", (), ts(3))
    h = Item("qr", 8, "issue", "Duda", "", frozenset({"needs:human"}), updated_at=ts(1))
    v = build_view(Snapshot(now=NOW, prs=[p], issues=[h]))
    assert v.waiting[0]["age"] == 3 * 3600 and v.human[0]["age"] == 3600 and v.human[0]["kind"] == "issue"
    assert build_view(Snapshot(now=NOW, prs=[pr(11)])).waiting[0]["age"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_view.py`
Expected: FAIL con `ImportError: cannot import name 'COLUMNS'`.

- [ ] **Step 3: Write minimal implementation**

En `view.py`, imports:

```python
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .config import DEFAULT_SLOTS
from .models import CLOSES_RE, LABEL_DEV, LABEL_DOCS, LABEL_FIX, LABEL_HUMAN, LABEL_QA, LABEL_REVIEW, LABEL_WORKING, Item, Slot
from .team_report import (DAY, clean_limits, clean_metrics, daily_hours, decision_alerts, flow_times, hour_strip,
                          rework_per_issue, slot_stats)
```

(`config.py` importa solo `models`, así que no hay ciclo.)

Constantes nuevas debajo de `ROLE_NAMES`:

```python
LABEL_EPIC = "epic"
COLUMNS = ("Por hacer", "Dev", "Review", "QA", "Fix", "Te espera")
RANGES = (7, 30)
```

`Snapshot`, campos nuevos al final:

```python
    repos: tuple[str, ...] = ()
    limits: list[dict[str, str]] = field(default_factory=list)
    slots: tuple[Slot, ...] = DEFAULT_SLOTS
    slot_costs: dict[str, float] = field(default_factory=dict)
    slot_labels: dict[str, str] = field(default_factory=dict)
    exhausted: dict[str, float] = field(default_factory=dict)
    closed: list[dict] = field(default_factory=list)
    merged: list[dict] = field(default_factory=list)
    image_usd: float = 0.04
    tz: str = "America/Argentina/Buenos_Aires"
```

`View`, campos nuevos al final:

```python
    slots: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    credentials: list[dict] = field(default_factory=list)
    budget: dict[str, dict] = field(default_factory=dict)
```

Funciones nuevas (antes de `build_view`):

```python
def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _age(now: float, iso_text: str) -> float | None:
    try:
        return max(0.0, now - datetime.fromisoformat(iso_text).timestamp())
    except (TypeError, ValueError):
        return None


def _hhmm(ts: float, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%H:%M")


def _column(stage: str) -> str:
    if stage in ("necesita a Eduardo", "espera a Eduardo"):
        return "Te espera"
    head = stage.split(" ", 1)[0]
    return {"fix": "Fix", "QA": "QA", "review": "Review", "dev": "Dev", "docs": "Dev"}.get(head, "Por hacer")


def _slot_cards(snap: Snapshot, rows: list, limits: list) -> list[dict]:
    tz, now = zone(snap.tz), snap.now
    day = slot_stats(rows, limits, snap.slots, {}, 0.0, now, DAY)
    week = slot_stats(rows, limits, snap.slots, {}, 0.0, now, 7 * DAY)
    cards = []
    for s in snap.slots:
        task = next(((k, t) for k, t in snap.active.items() if t.get("slot") == s.name), None)
        until = snap.exhausted.get(s.name, 0.0)
        active_since = None
        if task:
            key, t = task
            active_since = float(t.get("started_at", now))
            status, status_text = "trabajando", "Trabajando"
            role = ROLE_NAMES.get(t.get("role"), t.get("role"))
            detail = f"{role} de {key.replace('#', ' #')} · hace {int((now - active_since) // 60)} min"
        else:
            status, status_text = ("sin_cupo", f"Sin cupo hasta {_hhmm(until, tz)}") if until > now else ("libre", "Libre")
            done = [r for r in rows if r.get("puesto") == s.name]
            if done:
                last = max(done, key=lambda r: r["inicio"])
                end = datetime.fromisoformat(last.get("fin") or last["inicio"]).timestamp()
                role = ROLE_NAMES.get(last["rol"], last["rol"])
                detail = f"Terminó {role} de {last['repo']} #{last['numero']} a las {_hhmm(end, tz)}"
            else:
                detail = "Sin tareas registradas"
        strip = hour_strip(rows, limits, s.name, now, active_since, until if until > now else None)
        cells = [{"state": st, "title": f"{_hhmm(now - DAY + i * 3600, tz)} · {st.replace('_', ' ')}"}
                 for i, st in enumerate(strip)]
        hits = week[s.name].limit_hits
        footer = f"Uso en 7 días: {week[s.name].utilization:.0%} · {hits} {'corte' if hits == 1 else 'cortes'} en 7 días"
        if s.engine == "gemini":
            imgs = sum(int(r.get("imagenes_gemini") or 0) for r in rows if r.get("puesto") == s.name
                       and now - datetime.fromisoformat(r["inicio"]).timestamp() <= DAY)
            footer += f" · {imgs} imágenes en 24 h (USD {imgs * snap.image_usd:.2f})".replace(".", ",")
        cards.append({"name": s.name, "engine": s.engine, "label": snap.slot_labels.get(s.name) or f"{s.engine} · {s.tier}",
                      "status": status, "status_text": status_text, "detail": detail, "cells": cells,
                      "tasks": day[s.name].tasks, "hours": round(day[s.name].minutes / 60, 2),
                      "exhausted": round(day[s.name].exhausted_hours, 2), "footer": footer})
    return cards


def _budget(snap: Snapshot, rows: list, limits: list, days: int) -> dict:
    window, now = days * DAY, snap.now
    start = now - window
    stats = slot_stats(rows, limits, snap.slots, snap.slot_costs, snap.image_usd, now, window)
    in_window = [r for r in rows if datetime.fromisoformat(r["inicio"]).timestamp() >= start]
    images = sum(int(r.get("imagenes_gemini") or 0) for r in in_window)
    closed = [c for c in snap.closed if LABEL_EPIC not in (c.get("labels") or [])
              and (_age(now, c.get("closed_at")) or window + 1) <= window]
    cost = sum(s.cost_usd for s in stats.values())
    return {
        "days": days,
        "cost": cost,
        "fixed": sum(snap.slot_costs.get(s.name, 0.0) for s in snap.slots) * window / (30 * DAY),
        "images": images,
        "image_cost": images * snap.image_usd,
        "closed": len(closed),
        "cost_per_issue": cost / len(closed) if closed else None,
        "rework": rework_per_issue(in_window),
        "cuts": sum(1 for r in limits if datetime.fromisoformat(r["detectado"]).timestamp() >= start),
        "exhausted_hours": round(sum(s.exhausted_hours for s in stats.values()), 2),
        "daily": daily_hours(rows, [s.name for s in snap.slots], now, days, zone(snap.tz)),
        "exhausted": [{"slot": s.name, "engine": s.engine, "hours": round(stats[s.name].exhausted_hours, 2),
                       "cuts": stats[s.name].limit_hits} for s in snap.slots],
        "flow": flow_times(snap.merged, rows, now, window),
        "alerts": decision_alerts(limits, rows, snap.slots, now),
    }
```

En `build_view`:

1. En el `v.waiting.append({...})`, sumar `"age": _age(snap.now, p.updated_at)`.
2. En `v.human.append({...})`, sumar `"age": _age(snap.now, it.updated_at)` y `"kind": "pr" if isinstance(it, PRInfo) else "issue"`.
3. Reemplazar el bucle de `v.work` para saltear épicas y anotar la columna:

```python
    for it in sorted([*snap.issues, *snap.prs], key=lambda x: (x.repo, x.number)):
        if LABEL_EPIC in it.labels:
            continue
        kind = "pr" if isinstance(it, PRInfo) else "issue"
        deps = [d for d in parse_dependencies(it.body) if (it.repo, d) in open_issues] if kind == "issue" else []
        stage = _stage(it.labels, kind, snap.active.get(f"{it.repo}#{it.number}"), deps, snap.now)
        url = it.url if isinstance(it, PRInfo) else f"https://github.com/{snap.org}/{it.repo}/issues/{it.number}"
        v.work.setdefault(it.repo, []).append({"number": it.number, "kind": kind, "title": it.title, "url": url,
                                               "stage": stage, "column": _column(stage)})
```

4. Al final, antes de `return v`:

```python
    for name, exp in sorted(snap.expiries.items()):
        if exp is None:
            continue
        days = (exp - today).days
        level = "critico" if days < 7 else "advertencia" if days <= 30 else "ok"
        text = f"vencido hace {-days} días" if days < 0 else f"vence en {days} días ({exp.isoformat()})"
        v.credentials.append({"name": name, "level": level, "text": text})
    repos = list(snap.repos) or sorted(v.work)
    for repo in repos:
        epics = sorted((i for i in snap.issues if i.repo == repo and LABEL_EPIC in i.labels and i.sub_issues),
                       key=lambda i: i.number)
        epic = None
        if epics:
            e = epics[0]
            epic = {"number": e.number, "title": e.title, "url": f"https://github.com/{snap.org}/{repo}/issues/{e.number}",
                    "done": e.sub_issues[0], "total": e.sub_issues[1]}
        items = v.work.get(repo, [])
        counts = dict.fromkeys(COLUMNS, 0)
        for w in items:
            counts[w["column"]] += 1
        v.projects.append({"repo": repo, "epic": epic, "counts": counts, "items": items})
    rows, limits = clean_metrics(snap.metrics), clean_limits(snap.limits)
    v.slots = _slot_cards(snap, rows, limits)
    v.budget = {str(d): _budget(snap, rows, limits, d) for d in RANGES}
```

La variable `today` ya existe más arriba en `build_view` (se usa para `tokens`); dejar el bloque de credenciales después de ella.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`
Expected: PASS (todos; los tests viejos de `render` siguen pasando porque `render` todavía no cambió).

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/view.py dispatcher/tests/test_view.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(estado): datos de puestos, proyectos, credenciales y presupuesto en la vista

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: gráficos como HTML (`charts.py`)

**Files:**
- Create: `dispatcher/src/dispatcher/charts.py`
- Test: `dispatcher/tests/test_charts.py`

**Interfaces:**
- Produces:
  - `scale_top(max_hours: float) -> int`: tope par, mínimo 2;
  - `fmt_hours(h: float) -> str`: `"0 h"`, `"3,1 h"`, `"2 h"`;
  - `day_label(d: date, short: bool) -> str`: `"lun 12"` (corto) o `"lun 12 oct"`;
  - `stacked_bars(daily: list[dict], slots: list[tuple[str, str]], height: int = 200) -> str`: `slots` es `[(nombre, motor)]` en orden fijo;
  - `hbars(rows: list[dict]) -> str`: filas `{"label", "value", "fraction", "engine", "title"}`;
  - `strip_html(cells: list[dict], engine: str, aria: str) -> str`.

- [ ] **Step 1: Write the failing tests**

`dispatcher/tests/test_charts.py`:

```python
from datetime import date

from dispatcher.charts import day_label, fmt_hours, hbars, scale_top, stacked_bars, strip_html

SLOTS = [("claude-senior", "claude"), ("codex-senior", "codex"), ("gemini", "gemini")]


def test_scale_and_formats():
    assert [scale_top(x) for x in (0, 1.2, 2, 3.1, 7.9)] == [2, 2, 2, 4, 8]
    assert (fmt_hours(0), fmt_hours(3.14), fmt_hours(2)) == ("0 h", "3,1 h", "2 h")
    assert day_label(date(2026, 10, 12), True) == "lun 12" and day_label(date(2026, 10, 12), False) == "lun 12 oct"


def test_stacked_bars_heights_order_and_top_rounding():
    daily = [{"date": date(2026, 10, 11), "minutes": {"claude-senior": 60.0, "codex-senior": 120.0, "gemini": 0.0}},
             {"date": date(2026, 10, 12), "minutes": {"claude-senior": 0.0, "codex-senior": 0.0, "gemini": 0.0}}]
    html = stacked_bars(daily, SLOTS)
    assert html.count('class="seg') == 2                       # gemini en 0 no dibuja segmento
    assert 'height:48px;background:var(--c-claude)' in html    # 1 h de 4 h en 200 px, menos 2 de separación
    assert 'class="seg top" style="height:98px;background:var(--c-codex)' in html
    assert "dom 11 · claude-senior 1 h · codex-senior 2 h · gemini 0 h" in html
    assert ">4 h<" in html and ">0<" in html


def test_stacked_bars_30_days_labels_every_5():
    daily = [{"date": date(2026, 9, 13 + i) if i < 18 else date(2026, 10, i - 17), "minutes": {}} for i in range(30)]
    html = stacked_bars(daily, SLOTS)
    assert html.count('<span class="xl">') == 30 and html.count('<span class="xl"></span>') == 24


def test_hbars_and_strip():
    html = hbars([{"label": "codex-senior", "value": "9,5 h · 4 cortes", "fraction": 1.0, "engine": "codex", "title": "t"}])
    assert "width:100%" in html and "var(--c-codex)" in html and "9,5 h · 4 cortes" in html
    s = strip_html([{"state": "trabajando", "title": "06:00 · trabajando"}, {"state": "sin_cupo", "title": "<x>"},
                    {"state": "libre", "title": "a"}], "gemini", "gemini: 1 h")
    assert 'style="background:var(--c-gemini)"' in s and 'class="out"' in s and "&lt;x&gt;" in s and 'aria-label="gemini: 1 h"' in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_charts.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'dispatcher.charts'`.

- [ ] **Step 3: Write minimal implementation**

`dispatcher/src/dispatcher/charts.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_charts.py`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/charts.py dispatcher/tests/test_charts.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(estado): gráficos de barras y franja de 24 h en HTML

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: el HTML nuevo (`render.py`) y el resumen sin emojis

**Files:**
- Create: `dispatcher/src/dispatcher/render.py`
- Modify: `dispatcher/src/dispatcher/view.py` (borrar `CSS`, `_APP_STATES`, `_APP_HEALTH`, `_app_status`, `_a`, `_err` y `render`; queda `AGE_MARK`)
- Modify: `dispatcher/src/dispatcher/summary.py` (`render_summary`)
- Modify: `dispatcher/src/dispatcher/estado.py` (importar `render` de `.render`)
- Create: `dispatcher/tests/test_render.py`
- Modify: `dispatcher/tests/test_view.py` (sacar los tests de `render`, que pasan a `test_render.py`), `dispatcher/tests/test_estado.py` (import de `render`)

**Interfaces:**
- Consumes: la `View` de la tarea 4 y `charts.py` de la tarea 5.
- Produces: `render(view: View, rango: str = "7") -> str` y `render_all(view: View) -> dict[str, str]` (claves `"7"` y `"30"`), en `dispatcher.render`; `_app_status` se muda a `dispatcher.render`.

- [ ] **Step 1: Write the failing tests**

En `tests/test_view.py`, borrar `test_render_sections_and_empty_state`, `test_render_escapes_external_text`, `test_render_shows_source_errors`, `test_null_fields_from_coolify_do_not_break_view`, `test_github_down_never_says_nothing_pending`, `test_render_shows_linked_issue_and_dispatcher_error` y `test_app_status_traduce_estado_de_coolify`, y sacar `render` y `View` del import si quedan sin uso. Crear `tests/test_render.py`:

```python
import re
from datetime import date

from dispatcher.models import Item, Slot
from dispatcher.render import _app_status, render, render_all
from dispatcher.view import AppInfo, PRInfo, Snapshot, View, build_view
from dispatcher.watchdog import Check

NOW = 1_791_500_000.0
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
SLOTS3 = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))


def full_view():
    pr = PRInfo("qr", 10, "PR <b>diez</b>", "https://github.com/o/qr/pull/10", frozenset(), "Closes #3", "agent/3-x",
                "clean", "success", (), "2026-10-07T00:00:00+00:00")
    snap = Snapshot(now=NOW, repos=("qr",), slots=SLOTS3, prs=[pr],
                    issues=[Item("qr", 3, "issue", "Tres", "", frozenset()), Item("qr", 8, "issue", "Duda", "", frozenset({"needs:human"}))],
                    human_notes={"qr#8": "¿Qué medida?"}, exhausted={"gemini": NOW + 3600},
                    checks=[Check("Canvas", True, "ok"), Check("Dispatcher", False, "sin latido")],
                    apps=[AppInfo("qr-generator", "maxiar-org/qr", "https://qr.maxiar.dev", "running:healthy")],
                    expiries={"GITHUB_TOKEN": date(2026, 10, 30)}, ops=[(3, "[ops] canvas", "https://x/3")], tz="UTC")
    return build_view(snap)


def test_render_sections_in_design_order():
    html = render(full_view())
    titles = ["Estado del equipo", "Te esperan", "Equipo", "Proyectos", "Despliegues y credenciales", "Consumo y presupuesto", "Resumen"]
    positions = [html.index(t) for t in titles]
    assert positions == sorted(positions)
    assert "hace __EDAD__ s" in html and "fonts.googleapis.com" in html and "prefers-color-scheme:dark" in html


def test_render_escapes_external_text_and_has_no_emoji():
    html = render(full_view())
    assert "<b>diez</b>" not in html and "&lt;b&gt;diez&lt;/b&gt;" in html
    assert not EMOJI.search(html)


def test_render_marks_selected_range_and_reload_script():
    v = full_view()
    assert 'href="?rango=7" aria-current="page"' in render(v, "7")
    assert 'href="?rango=30" aria-current="page"' in render(v, "30")
    assert "details[open]" in render(v)
    assert set(render_all(v)) == {"7", "30"}
    assert render(v, "99") == render(v, "7")


def test_render_team_cards_and_waiting():
    html = render(full_view())
    assert "Sin cupo hasta" in html and "var(--c-gemini)" in html and "claude-senior" in html
    assert "Decidir" in html and "¿Qué medida?" in html and "Revisar y mergear" in html and "hace 5 d" in html
    assert "[ops] canvas" in html and "vence en" in html


def test_empty_view_says_nothing_pending():
    html = render(View(updated=NOW))
    assert "Nada pendiente" in html and "Nada para decidir" in html


def test_github_down_never_says_nothing_pending():
    html = render(build_view(Snapshot(now=NOW, errors={"github": "ConnectError"})))
    assert "Nada pendiente" not in html and html.count("sin datos (ConnectError)") == 2


def test_render_shows_source_errors_and_null_coolify_fields():
    assert "sin datos (ConnectError)" in render(View(updated=NOW, errors={"coolify": "ConnectError"}))
    assert "img" in render(build_view(Snapshot(now=NOW, apps=[AppInfo("img", "", "", "")])))


def test_render_shows_linked_issue_and_dispatcher_error():
    v = build_view(Snapshot(now=NOW, prs=[PRInfo("qr", 10, "t", "u", frozenset(), "", "agent/3-x")],
                            issues=[Item("qr", 3, "issue", "Tres", "", frozenset())], errors={"dispatcher": "JSONDecodeError"}))
    html = render(v)
    assert "https://github.com/maxiar-org/qr/issues/3" in html and "sin datos (JSONDecodeError)" in html


def test_app_status_traduce_estado_de_coolify():
    assert _app_status("running:unknown") == ("ok", "Corriendo (sin healthcheck)")
    assert _app_status("running:healthy") == ("ok", "Corriendo (sana)")
    assert _app_status("running:unhealthy") == ("bad", "Corriendo (con fallas)")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_render.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'dispatcher.render'`.

- [ ] **Step 3: Write minimal implementation**

`summary.py`, reemplazar `render_summary`:

```python
def render_summary(summary: dict | None, error: str | None, now: float) -> str:
    last = (summary or {}).get("last")
    when = (f'<span class="muted">Generado {_fmt(last.get("generated_at"))} · cubre desde {_fmt(last.get("since"))}</span>'
            if last else "")
    out = [f'<section class="card" aria-labelledby="h-resumen"><div class="sec-head"><h2 id="h-resumen">Resumen</h2>{when}</div>',
           NOTICE_MARK]
    if error:
        out.append(f'<p class="bad">sin datos ({escape(error)})</p>')
    if summary:
        if summary.get("error"):
            out.append(f'<p class="bad">Atención: el último pedido falló: {escape(str(summary["error"])[:300])}</p>')
        if last:
            out.append(f'<div class="prose">{md_to_html(last.get("markdown", ""))}</div>')
        else:
            out.append('<p class="muted">Todavía no hay resúmenes.</p>')
    if summary and summary.get("status") == "running":
        started = summary.get("started_at") or now
        out.append(f'<p class="warn">generando… hace {max(0, int(now - started))} s</p>')
    else:
        out.append('<form method="post" action="/resumen"><button type="submit" class="btn">Pedir resumen</button></form>')
    out.append("</section>")
    return "".join(out)
```

En `estado.py`, `Page.body`: el aviso pasa a `f'<p class="bad">Aviso: {escape(notice[:300])}</p>'`; e importar `from .render import render` (sacar `render` del import de `.view`).

`view.py`: borrar desde `CSS = """` hasta el final del archivo, salvo `AGE_MARK = "__EDAD__"`, que se queda.

`dispatcher/src/dispatcher/render.py`:

```python
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
a{color:inherit}.mono{font-family:"Geist Mono",ui-monospace,monospace}.muted{color:var(--muted);font-size:13px}.ink2{color:var(--ink2)}
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


def _header(view: View) -> str:
    pills = "".join(f'<span class="pill" title="{escape(c.detail, quote=True)}">{ICONS["ok" if c.ok else "critical"]}'
                    f'{escape(c.name)}</span>' for c in view.health)
    running = (view.summary or {}).get("status") == "running"
    button = "" if running else '<form method="post" action="/resumen"><button type="submit" class="btn">Pedir resumen</button></form>'
    return (f'<header class="top"><div><div class="eyebrow">maxiar-org · AI Dev Team</div><h1>Estado del equipo</h1>'
            f'<div class="muted">Actualizado hace {AGE_MARK} s · se refresca cada 60 s</div></div>'
            f'<div class="pills">{pills}{button}</div></header>' + _err(view, "salud"))


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
        body.append(f'<tr><th scope="row" class="l"><div class="mono" style="font-size:14px">{escape(p["repo"])}</div>'
                    f'{epic}{details}</th>{"".join(cells)}</tr>')
    return (f'<section class="card wide" aria-labelledby="h-proyectos"><div class="sec-head"><h2 id="h-proyectos">Proyectos</h2>'
            f'<span class="muted">Issues y PR abiertos por etapa</span></div>{_err(view, "github")}<div class="scroll">'
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
    return (f'<section class="card" aria-labelledby="h-consumo">{head}{errors}<div class="tiles">{tiles_html}</div>'
            f'<div class="charts"><figure class="wide"><div class="sec-head"><figcaption>Horas de trabajo por día y puesto</figcaption>'
            f'<div class="legend">{legend}</div></div><div role="img" aria-label="{escape(aria, quote=True)}">'
            f'{stacked_bars(b["daily"], slots)}</div>{table}</figure>'
            f'<div class="narrow"><figure><figcaption>Horas sin cupo por puesto</figcaption>{hb}</figure>'
            f'<div style="display:flex;flex-direction:column;gap:10px"><h3>Tiempos de flujo <span class="muted">· mediana</span></h3>{flow}</div></div></div>'
            f'<div style="display:flex;flex-direction:column;gap:10px"><h3>Para decidir</h3>{alerts}</div></section>')


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
```

En `estado.py`, el import queda `from .view import AGE_MARK, PRInfo, Snapshot, awaits_human, build_view` y `from .render import render`. En `tests/test_estado.py`, cambiar `from dispatcher.view import Snapshot, View, build_view, render` por `from dispatcher.view import Snapshot, View, build_view` y `from dispatcher.render import render`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`
Expected: PASS. Si `tests/test_summary.py::test_render_summary_states` falla por `"el último pedido falló: TimeoutExpired"`, revisar que la frase siga en minúscula después de "Atención: ".

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/render.py dispatcher/src/dispatcher/view.py dispatcher/src/dispatcher/summary.py dispatcher/src/dispatcher/estado.py dispatcher/tests/test_render.py dispatcher/tests/test_view.py dispatcher/tests/test_estado.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(estado): HTML nuevo con el diseño de Claude Design

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: el servicio (`estado.py`): fuentes nuevas, rangos y `/api/estado`

**Files:**
- Modify: `dispatcher/src/dispatcher/estado.py`
- Test: `dispatcher/tests/test_estado.py`

**Interfaces:**
- Consumes: `render_all` (tarea 6), los campos nuevos de `Snapshot` (tarea 4), `parse_slots`, `parse_slot_costs` y `parse_slot_labels` (tarea 1), `LimitLog` (`metrics.py`).
- Produces:
  - `Collector(..., limits_path=None, slots=DEFAULT_SLOTS, slot_costs=None, slot_labels=None, image_usd=0.04, tz="America/Argentina/Buenos_Aires", search_every=600)`;
  - `Page.update(html: str | dict[str, str], generated_at, view=None)`, `Page.body(now, notice=None, rango="7")`, `Page.api() -> tuple[int, bytes]`;
  - `GET /api/estado`.

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/test_estado.py`:

```python
import json

from dispatcher.estado import refresh
from dispatcher.metrics import LimitLog
from dispatcher.models import Slot


class SearchGH(GH):
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def search_since(self, query):
        self.calls += 1
        if self.fail:
            raise RuntimeError("search caído")
        if "is:pr" in query:
            return [{"repo": "qr", "number": 9, "created_at": "2026-10-12T01:00:00Z", "merged_at": "2026-10-12T03:00:00Z", "closes": 1}]
        return [{"repo": "qr", "number": 1, "closed_at": "2026-10-12T03:00:00Z", "labels": []}]


def collector(tmp_path, gh, **kw):
    return Collector(gh, None, repos=("qr",), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                     state_path=tmp_path / "state.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={},
                     limits_path=tmp_path / "limits.csv", **kw)


def test_collector_reads_exhaustion_limits_and_slots(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"active": {}, "slot_exhausted_until": {"gemini": 1234.5}}))
    LimitLog(tmp_path / "limits.csv").append("gemini", "gemini", 900.0, 1234.5, "qr#1", "429")
    slots = (Slot("gemini", "gemini", "senior"),)
    snap = collector(tmp_path, SearchGH(), slots=slots, slot_costs={"gemini": 20.0}, slot_labels={"gemini": "Gemini Pro"},
                     tz="UTC").collect(now=1000.0)
    assert snap.exhausted == {"gemini": 1234.5} and len(snap.limits) == 1 and snap.repos == ("qr",)
    assert (snap.slots, snap.slot_costs, snap.slot_labels, snap.tz) == (slots, {"gemini": 20.0}, {"gemini": "Gemini Pro"}, "UTC")
    assert [m["number"] for m in snap.merged] == [9] and [c["number"] for c in snap.closed] == [1]


def test_period_searches_are_cached(tmp_path):
    gh = SearchGH()
    c = collector(tmp_path, gh)
    c.collect(now=1000.0)
    c.collect(now=1500.0)
    assert gh.calls == 2
    c.collect(now=1700.0)
    assert gh.calls == 4


def test_period_cache_survives_search_error(tmp_path):
    gh = SearchGH()
    c = collector(tmp_path, gh)
    c.collect(now=1000.0)
    gh.fail = True
    snap = c.collect(now=2000.0)
    assert "consumo" in snap.errors and [m["number"] for m in snap.merged] == [9]


def test_unknown_rango_falls_back_to_7():
    page = Page()
    page.update({"7": "siete", "30": "treinta"}, 1000.0)
    assert page.body(1000.0, rango="30") == "treinta" and page.body(1000.0, rango="x") == "siete"
    page.update("solo", 1000.0)
    assert page.body(1000.0, rango="30") == "solo"


def test_api_returns_view_json(tmp_path):
    page = Page()
    assert page.api()[0] == 503
    refresh(page, collector(tmp_path, SearchGH(), tz="UTC"), 1000.0)
    code, body = page.api()
    data = json.loads(body)
    assert code == 200 and set(data["budget"]) == {"7", "30"} and "slots" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q tests/test_estado.py`
Expected: FAIL con `TypeError: Collector.__init__() got an unexpected keyword argument 'limits_path'`.

- [ ] **Step 3: Write minimal implementation**

Imports nuevos en `estado.py`:

```python
from dataclasses import asdict
from datetime import datetime, timezone

from .config import DEFAULT_SLOTS, parse_slot_costs, parse_slot_labels, parse_slots
from .metrics import LimitLog, MetricsLog
from .render import render_all
```

(y sacar el `from .render import render` de la tarea 6 si `render` ya no se usa).

`Collector.__init__`:

```python
    def __init__(self, github, coolify, repos, org, bot_login, ops_repo, state_path: Path, metrics_path: Path,
                 checker: Callable[[], list], expiries: dict, resumen=None, limits_path: Path | None = None,
                 slots=DEFAULT_SLOTS, slot_costs=None, slot_labels=None, image_usd: float = 0.04,
                 tz: str = "America/Argentina/Buenos_Aires", search_every: float = 600):
        self.github, self.coolify, self.repos, self.org = github, coolify, repos, org
        self.bot_login, self.ops_repo = bot_login, ops_repo
        self.state_path, self.metrics_path, self.checker, self.expiries = state_path, metrics_path, checker, expiries
        self.resumen = resumen
        self.limits_path, self.slots, self.image_usd, self.tz = limits_path, tuple(slots), image_usd, tz
        self.slot_costs, self.slot_labels = dict(slot_costs or {}), dict(slot_labels or {})
        self.search_every = search_every
        self._period: tuple[float, list, list] | None = None  # (cuándo, cerrados, mergeados): búsquedas de GitHub cacheadas
```

En `collect`, el `Snapshot` se crea con los datos de configuración:

```python
        snap = Snapshot(now=now, org=self.org, expiries=self.expiries, repos=tuple(self.repos), slots=self.slots,
                        slot_costs=self.slot_costs, slot_labels=self.slot_labels, image_usd=self.image_usd, tz=self.tz)
```

La sección `dispatcher` lee también el agotamiento:

```python
        def dispatcher() -> None:
            if self.state_path.exists():
                data = json.loads(self.state_path.read_text())
                snap.active = data.get("active", {})
                snap.exhausted = {k: float(v) for k, v in data.get("slot_exhausted_until", {}).items()}
```

Sección nueva, registrada después de `salud` con `section("consumo", consumo)`:

```python
        def consumo() -> None:
            if self.limits_path is not None:
                snap.limits = LimitLog(self.limits_path).read()
            try:
                if self._period is None or now - self._period[0] >= self.search_every:
                    since = datetime.fromtimestamp(now - 30 * 86400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    closed = self.github.search_since(f"org:{self.org} is:issue is:closed closed:>={since}")
                    merged = self.github.search_since(f"org:{self.org} is:pr is:merged merged:>={since}")
                    self._period = (now, closed, merged)
            finally:
                if self._period is not None:  # si GitHub falla, se muestran los datos de la última búsqueda buena
                    snap.closed, snap.merged = self._period[1], self._period[2]
```

`Page`:

```python
class Page:
    """Último HTML generado por rango (y su vista); la antigüedad y el aviso se completan en cada pedido."""

    def __init__(self) -> None:
        self.html = {"7": "<!doctype html><meta charset=utf-8><p>Cargando…</p>"}
        self.generated_at = time.time()
        self.view = None
        self.lock = threading.Lock()  # el hilo de recolección y los pedidos HTTP la actualizan

    def update(self, html: str | dict[str, str], generated_at: float, view=None) -> None:
        with self.lock:
            self.html = dict(html) if isinstance(html, dict) else {"7": html}
            self.generated_at = generated_at
            if view is not None:
                self.view = view

    def body(self, now: float, notice: str | None = None, rango: str = "7") -> str:
        aviso = f'<p class="bad">Aviso: {escape(notice[:300])}</p>' if notice else ""
        html = self.html.get(rango) or self.html["7"]
        return html.replace(AGE_MARK, str(max(0, int(now - self.generated_at)))).replace(NOTICE_MARK, aviso)

    def api(self) -> tuple[int, bytes]:
        view = self.view
        if view is None:
            return 503, b'{"error": "sin datos"}'
        return 200, json.dumps(asdict(view), default=str, ensure_ascii=False).encode()
```

`refresh`: `page.update(render_all(view), now, view)`. `refresh_summary`: `html = render_all(view)` y, dentro del lock, `page.html = html`.

`do_GET`:

```python
        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, b"ok")
            if url.path == "/api/estado":
                code, body = page.api()
                return self._send(code, body, "application/json; charset=utf-8")
            if page.view is not None and (page.view.summary or {}).get("status") == "running":
                refresh_summary(page, resumen, time.time())
            query = parse_qs(url.query)
            notice = query.get("error", [None])[0]
            rango = query.get("rango", ["7"])[0]
            self._send(200, page.body(time.time(), notice, rango).encode(), "text/html; charset=utf-8")
```

`main()`, en la creación del `Collector`:

```python
    slots = parse_slots(env)
    collector = Collector(
        github, coolify, tuple(r.strip() for r in env["REPOS"].split(",") if r.strip()), org,
        env.get("BOT_LOGIN", "maxiar-ai-dev-team-bot"), env.get("OPS_REPO", "ai-dev-team"),
        Path(env.get("STATE_PATH", "/state/state.json")), Path(env.get("METRICS_PATH", "/pilot/metrics.csv")), checker,
        {"GITHUB_TOKEN": parse_expiry(env.get("GITHUB_TOKEN_EXPIRES")),
         "CLAUDE_CODE_OAUTH_TOKEN": parse_expiry(env.get("CLAUDE_TOKEN_EXPIRES"))},
        resumen=resumen,
        limits_path=Path(env.get("LIMITS_PATH", "/pilot/limits.csv")),
        slots=slots, slot_costs=parse_slot_costs(env, slots), slot_labels=parse_slot_labels(env, slots),
        image_usd=float(env.get("GEMINI_IMAGE_USD", "").strip() or 0.04),
        tz=env.get("ESTADO_TZ", "").strip() or "America/Argentina/Buenos_Aires",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`
Expected: PASS. Si `test_notice_is_escaped_and_shown_once` buscaba el emoji del aviso, ajustarlo a `"Aviso: "`.

- [ ] **Step 5: Commit**

```bash
git add dispatcher/src/dispatcher/estado.py dispatcher/tests/test_estado.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(estado): agotamiento, cortes, búsquedas cacheadas, rango por URL y /api/estado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: compose, README, página de ejemplo y revisión visual

**Files:**
- Modify: `docker-compose.yml` (servicio `estado`)
- Modify: `README.md` (sección de la vista de estado y "Puestos del equipo")
- Create: `scripts/estado-demo.py`

**Interfaces:**
- Consumes: `build_view`, `render_all`, `Snapshot`, `Slot`, `Check`, `AppInfo`, `PRInfo`, `Item`.

- [ ] **Step 1: compose**

En `docker-compose.yml`, servicio `estado`, `environment`, debajo de `METRICS_PATH`:

```yaml
      LIMITS_PATH: /pilot/limits.csv
      # Puestos (fase 5a) para la pantalla de equipo y presupuesto (fase 5b).
      SLOTS: ${SLOTS:-}
      SLOT_COST_CLAUDE_SENIOR: ${SLOT_COST_CLAUDE_SENIOR:-}
      SLOT_COST_CODEX_SENIOR: ${SLOT_COST_CODEX_SENIOR:-}
      SLOT_COST_GEMINI: ${SLOT_COST_GEMINI:-}
      SLOT_LABEL_CLAUDE_SENIOR: ${SLOT_LABEL_CLAUDE_SENIOR:-}
      SLOT_LABEL_CODEX_SENIOR: ${SLOT_LABEL_CODEX_SENIOR:-}
      SLOT_LABEL_GEMINI: ${SLOT_LABEL_GEMINI:-}
      GEMINI_IMAGE_USD: ${GEMINI_IMAGE_USD:-0.04}
      ESTADO_TZ: ${ESTADO_TZ:-America/Argentina/Buenos_Aires}  # zona en la que la pantalla muestra las horas
```

Verificar: `docker compose config -q && echo ok` desde la raíz del repo (con un `.env` de prueba si hace falta: `REPOS=x GITHUB_TOKEN=x CANVAS_API_KEY=x docker compose config -q`).
Expected: `ok`.

- [ ] **Step 2: página de ejemplo**

`scripts/estado-demo.py`:

```python
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
```

Run: `cd dispatcher && uv run python ../scripts/estado-demo.py /private/tmp/estado-demo`
Expected: `Escribí /private/tmp/estado-demo/estado-7.html y estado-30.html`.

- [ ] **Step 3: revisión visual contra el diseño**

Abrir los dos HTML con Playwright (o el navegador) en tres tamaños: 1440 × 900 claro, 1440 × 900 con `prefers-color-scheme: dark` y 390 × 844. Comparar contra el canvas (https://claude.ai/artifact/RrUtD84BVcAAbyqCEAuL4r):
- el orden de secciones y la jerarquía de títulos;
- los colores de puesto, las franjas y las barras;
- en 390 px: sin scroll horizontal de la página (`document.documentElement.scrollWidth <= 390`), con la tabla de proyectos scrolleando en su caja.

Corregir en `render.py` lo que no coincida, con `pytest` en verde después de cada cambio.

- [ ] **Step 4: README**

En `README.md`, en la sección de la vista de estado (buscar `estado.maxiar.dev`), agregar:

```markdown
**Pantalla (fase 5b):** te esperan, equipo por puesto (estado, franja de 24 h, consumo), proyectos por etapa con la épica en curso, despliegues y credenciales, consumo y presupuesto (`?rango=7` o `?rango=30`) y el resumen del operador. `GET /api/estado` devuelve los mismos datos en JSON (detrás de Access).

Variables del servicio `estado`, además de las de siempre: `SLOTS`, `SLOT_COST_<PUESTO>`, `SLOT_LABEL_<PUESTO>` (la línea de plan bajo el nombre del puesto), `GEMINI_IMAGE_USD`, `LIMITS_PATH` y `ESTADO_TZ` (zona de las horas que se muestran, por defecto `America/Argentina/Buenos_Aires`).

Para revisar el diseño sin la mini-PC: `cd dispatcher && uv run python ../scripts/estado-demo.py /tmp/estado` y abrir los HTML.
```

Y en "Puestos del equipo", debajo del bloque de `.env`, una línea: `SLOT_LABEL_CLAUDE_SENIOR="Claude Max 5x · arquitectura"   # opcional, para la pantalla de estado`.

- [ ] **Step 5: Run tests and commit**

Run: `cd dispatcher && uv run --with pytest --with respx python -m pytest -q`
Expected: PASS.

```bash
git add docker-compose.yml README.md scripts/estado-demo.py dispatcher/src/dispatcher/render.py
git -c user.email=eduardo.jimenez@falconsoft.cl commit -m "feat(estado): variables del compose, página de ejemplo y documentación

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: despliegue (después del merge de Eduardo)

No es código: se hace cuando Eduardo mergea el PR.

- [ ] **Step 1:** `ssh ubuntu-labs 'cd /opt/ai-dev-team && sudo -u aidev git pull'`.
- [ ] **Step 2:** sumar al `.env` de la mini-PC, con backup previo, `SLOT_LABEL_CLAUDE_SENIOR`, `SLOT_LABEL_CODEX_SENIOR` y `SLOT_LABEL_GEMINI` (texto que elija Eduardo).
- [ ] **Step 3:** sin tareas activas (`state.json` → `active` vacío), `docker compose build dispatcher && docker compose up -d dispatcher estado`.
- [ ] **Step 4:** `curl -s localhost` no aplica (estado no publica puertos): verificar con `docker compose exec estado python -c "import urllib.request,socket; h=socket.gethostbyname('estado-publico'); print(urllib.request.urlopen(f'http://{h}:8090/api/estado').status)"`. Expected: `200`.
- [ ] **Step 5:** Eduardo recorre `https://estado.maxiar.dev` en la compu y el celular. Entrada en `docs/bitacora.md`.
