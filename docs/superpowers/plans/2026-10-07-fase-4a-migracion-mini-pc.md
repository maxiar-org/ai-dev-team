# Fase 4a: migración a la mini-PC, autonomía y operador remoto (plan de implementación)

> **Para agentes que ejecuten este plan:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementarlo tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguir el avance.

**Objetivo:** mover el AI Dev Team a la mini-PC (`ssh ubuntu-labs`) con todo dentro de Docker Compose, sumando un túnel de Cloudflare, un watchdog con alertas en issues `ops` y un operador de Claude Code con Remote Control.

**Arquitectura:** al compose actual (`canvas` y `dispatcher`) se le suman tres servicios:
- `cloudflared`: el túnel con nombre hacia `canvas.maxiar.dev`;
- `watchdog`: la misma imagen del dispatcher, con el comando `python -m dispatcher.watchdog`;
- `operador`: una imagen propia con Claude Code, `gh`, `tmux` y el cliente de Docker.

El dispatcher escribe un latido en cada ciclo. En el host solo hay Docker.

**Stack:** Docker Engine y Compose en Ubuntu 26.04, Python 3.12 (pytest, respx, httpx), Cloudflare Tunnel y Access, Claude Code CLI (Remote Control) y GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-10-07-fase-4a-migracion-mini-pc-design.md`

## Restricciones globales

- **Todo corre en Docker Compose; en el host solo hay Docker.** No se crean servicios de `systemd` ni timers propios.
- No se toca `hermes` (`192.168.1.101:9119`) ni nada fuera del proyecto Compose `ai-dev-team`.
- No se publican puertos en la IP de la LAN. Canvas sigue en `127.0.0.1:8000`, y el acceso externo es solo por el túnel.
- El repo vive en `/opt/ai-dev-team`, con dueño `aidev`. El `.env` tiene permisos `600` y nunca va a git.
- Las alertas son issues en `maxiar-org/ai-dev-team` con el label `ops` y títulos `[ops] <chequeo>`.
- El operador usa la cuenta de Claude personal de Eduardo, no la Pro de los agentes.
- El corte es así: se detiene el dispatcher de la Mac **antes** de levantar el de la mini-PC, y solo cuando no hay tareas activas.

## Foco de revisión

1. **Un chequeo que falla en ciclos seguidos:** se abre un solo issue, no uno por ciclo. Test: `test_failing_check_opens_one_issue_only` (tarea 2).
2. **Un latido ilegible o ausente**, por ejemplo cuando el dispatcher todavía no hizo su primer ciclo: cuenta como falla con un detalle claro, no rompe el watchdog. Test: `test_missing_or_garbage_heartbeat_fails_cleanly` (tarea 2).
3. **GitHub caído mientras corre el watchdog:** el ciclo registra el error en el log y sigue. Test: `test_github_errors_do_not_crash_watchdog_cycle` (tarea 2).
4. **Fechas de vencimiento vacías o mal escritas en `.env`:** se ignoran con una advertencia en lugar de crashear. Test: `test_bad_expiry_dates_are_ignored` (tarea 2).
5. **El latido no se escribe cuando el ciclo falla antes de terminar,** para que el watchdog lo detecte: el latido se escribe solo al final de un ciclo completo. Test: `test_heartbeat_written_only_after_successful_cycle` (tarea 1).

---

### Tarea 1: Latido del dispatcher

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/config.py`, `dispatcher/src/dispatcher/runner.py`
- Tests: `dispatcher/tests/test_runner.py`, `dispatcher/tests/test_config.py`

**Interfaces:**
- Produce: `Config.heartbeat_path: Path | None`. `from_env` lee `HEARTBEAT_PATH` (por defecto `/state/heartbeat`, y vacío desactiva). Después de un ciclo completo, el runner escribe `str(now)` en ese archivo.

- [ ] **Paso 1: Tests que fallan.**

  En `test_config.py`:

```python
def test_heartbeat_path_default_and_disable():
    assert str(Config.from_env(BASE).heartbeat_path) == "/state/heartbeat"
    assert Config.from_env({**BASE, "HEARTBEAT_PATH": ""}).heartbeat_path is None
```

  En `test_runner.py`:

```python
def test_heartbeat_written_only_after_successful_cycle(tmp_path, cfg):
    import dataclasses

    hb = tmp_path / "hb"
    cfg2 = dataclasses.replace(cfg, heartbeat_path=hb)
    d, gh, cv, ws, clock = make(tmp_path, cfg2)
    d.run_once()
    assert hb.read_text() == "10000.0"
    clock.now += 60
    gh.list_open_items = lambda repo: (_ for _ in ()).throw(RuntimeError("GitHub caído"))
    try:
        d.run_once()
    except RuntimeError:
        pass
    assert hb.read_text() == "10000.0"
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q tests/test_config.py tests/test_runner.py`. Resultado esperado: FAIL (`heartbeat_path`).

- [ ] **Paso 3: Implementar.**
  - **`config.py`:** agregar el campo `heartbeat_path: Path | None = None`. En `from_env`:

```python
            heartbeat_path=Path(hb) if (hb := env.get("HEARTBEAT_PATH", "/state/heartbeat").strip()) else None,
```

  - **`runner.py`:** al final de `run_once`, justo antes de `return actions`, agregar:

```python
        if self.cfg.heartbeat_path is not None:
            # El watchdog usa este latido para saber que el dispatcher completa ciclos.
            self.cfg.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            self.cfg.heartbeat_path.write_text(str(now))
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5:** commit con el mensaje `feat(dispatcher): latido al final de cada ciclo`.

---

### Tarea 2: Watchdog

**Archivos:**
- Crear: `dispatcher/src/dispatcher/watchdog.py`
- Modificar: `dispatcher/src/dispatcher/github.py`
- Tests: `dispatcher/tests/test_watchdog.py`, `dispatcher/tests/test_github.py`

**Interfaces:**
- Produce:
  - `Check(name, ok, detail="")`, `OpenOps(title, body)`, `CloseOps(number, comment)`
  - `plan_ops(checks, expiries, open_issues, today, warn_days=14) -> list[OpenOps | CloseOps]`
  - `parse_expiry(value) -> date | None`
  - `run_checks(...) -> list[Check]`
  - `Watchdog.run_once()` y `main()`
  - En `GitHubClient`:
    - `list_open_issue_titles(repo, label) -> dict[str, int]`
    - `create_issue(repo, title, body, labels)`
    - `close_issue(repo, number, comment)`

- [ ] **Paso 1: Tests que fallan.** Crear `dispatcher/tests/test_watchdog.py`:

```python
from datetime import date

import httpx
import respx

from dispatcher.watchdog import Check, CloseOps, OpenOps, Watchdog, parse_expiry, plan_ops, run_checks

TODAY = date(2026, 10, 7)


def test_failing_check_opens_one_issue_only():
    checks = [Check("canvas", False, "HTTP 502"), Check("dispatcher", True)]
    first = plan_ops(checks, {}, {}, TODAY)
    assert first == [OpenOps("[ops] canvas", first[0].body)] and "HTTP 502" in first[0].body
    assert plan_ops(checks, {}, {"[ops] canvas": 12}, TODAY) == []


def test_recovered_check_closes_its_issue():
    [op] = plan_ops([Check("canvas", True)], {}, {"[ops] canvas": 12}, TODAY)
    assert isinstance(op, CloseOps) and op.number == 12 and "recuperó" in op.comment


def test_expiry_warning_once_within_14_days():
    exp = {"GITHUB_TOKEN": date(2026, 10, 20), "CLAUDE_CODE_OAUTH_TOKEN": date(2027, 10, 4)}
    [op] = plan_ops([], exp, {}, TODAY)
    assert op.title == "[ops] Renovar GITHUB_TOKEN (vence 2026-10-20)"
    assert plan_ops([], exp, {op.title: 5}, TODAY) == []


def test_bad_expiry_dates_are_ignored():
    assert parse_expiry("") is None
    assert parse_expiry("no-es-fecha") is None
    assert parse_expiry("2027-01-01") == date(2027, 1, 1)


def test_missing_or_garbage_heartbeat_fails_cleanly(tmp_path):
    hb = tmp_path / "heartbeat"
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert not checks["dispatcher"].ok and "no existe" in checks["dispatcher"].detail
        hb.write_text("basura")
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert not checks["dispatcher"].ok
        hb.write_text("900.0")
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert checks["dispatcher"].ok and checks["canvas"].ok and checks["disco"].ok
        assert "tunel" not in checks


def test_canvas_and_tunnel_failures(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").mock(side_effect=httpx.ConnectError("refused"))
        respx.get("http://cloudflared:2000/ready").respond(503)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "http://cloudflared:2000/ready", str(tmp_path), now=1000.0)}
    assert not checks["canvas"].ok and "refused" in checks["canvas"].detail
    assert not checks["tunel"].ok and "503" in checks["tunel"].detail


class FakeGH:
    def __init__(self, fail=False):
        self.created, self.closed, self.fail = [], [], fail

    def list_open_issue_titles(self, repo, label):
        if self.fail:
            raise httpx.ConnectError("sin red")
        return {}

    def create_issue(self, repo, title, body, labels):
        self.created.append(title)

    def close_issue(self, repo, number, comment):
        self.closed.append(number)


def test_github_errors_do_not_crash_watchdog_cycle():
    wd = Watchdog(FakeGH(fail=True), "ai-dev-team", lambda: [Check("canvas", False, "x")], {}, today=lambda: TODAY)
    assert wd.run_once() == []


def test_watchdog_cycle_creates_issue_with_ops_label():
    gh = FakeGH()
    wd = Watchdog(gh, "ai-dev-team", lambda: [Check("canvas", False, "x")], {}, today=lambda: TODAY)
    wd.run_once()
    assert gh.created == ["[ops] canvas"]
```

  Agregar a `dispatcher/tests/test_github.py`:

```python
@respx.mock
def test_ops_issue_helpers(gh):
    respx.route(method="GET", host=HOST, path="/repos/maxiar-org/qr/issues").respond(
        json=[{"number": 4, "title": "[ops] canvas"}, {"number": 5, "title": "PR", "pull_request": {}}]
    )
    created = route("POST", "/issues").respond(201, json={"number": 6})
    commented = route("POST", "/issues/4/comments").respond(201, json={})
    closed = route("PATCH", "/issues/4").respond(200, json={})
    assert gh.list_open_issue_titles("qr", "ops") == {"[ops] canvas": 4}
    gh.create_issue("qr", "[ops] x", "cuerpo", ["ops"])
    gh.close_issue("qr", 4, "recuperado")
    assert json.loads(created.calls.last.request.content) == {"title": "[ops] x", "body": "cuerpo", "labels": ["ops"]}
    assert json.loads(commented.calls.last.request.content) == {"body": "recuperado"}
    assert json.loads(closed.calls.last.request.content) == {"state": "closed"}
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q tests/test_watchdog.py tests/test_github.py`. Resultado esperado: FAIL (`ModuleNotFoundError: dispatcher.watchdog`).

- [ ] **Paso 3: Implementar.**

  **`github.py`:** agregar a `GitHubClient`:

```python
    def list_open_issue_titles(self, repo: str, label: str) -> dict[str, int]:
        raw = self._paginate(f"{self._repo(repo)}/issues", {"state": "open", "labels": label, "per_page": 100})
        return {i["title"]: i["number"] for i in raw if "pull_request" not in i}

    def create_issue(self, repo: str, title: str, body: str, labels: Iterable[str]) -> None:
        resp = self.http.post(f"{self._repo(repo)}/issues", json={"title": title, "body": body, "labels": list(labels)})
        resp.raise_for_status()

    def close_issue(self, repo: str, number: int, comment: str) -> None:
        self.comment(repo, number, comment)
        resp = self.http.patch(f"{self._repo(repo)}/issues/{number}", json={"state": "closed"})
        resp.raise_for_status()
```

  **`watchdog.py`** (nuevo):

```python
"""Watchdog del stack: chequea Canvas, el latido del dispatcher, el túnel y el disco, y abre o cierra
issues [ops] en GitHub. Corre como servicio del compose (python -m dispatcher.watchdog)."""

from __future__ import annotations

import logging
import os
import shutil
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from .github import GitHubClient

log = logging.getLogger("watchdog")
HEARTBEAT_MAX_AGE = 300
DISK_MAX_USED = 0.85


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class OpenOps:
    title: str
    body: str


@dataclass(frozen=True)
class CloseOps:
    number: int
    comment: str


def parse_expiry(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        if (value or "").strip():
            log.warning("Fecha de vencimiento inválida: %r (se ignora)", value)
        return None


def plan_ops(
    checks: Iterable[Check],
    expiries: Mapping[str, date | None],
    open_issues: Mapping[str, int],
    today: date,
    warn_days: int = 14,
) -> list[OpenOps | CloseOps]:
    """Función pura: qué issues [ops] abrir o cerrar."""
    ops: list[OpenOps | CloseOps] = []
    for check in checks:
        title = f"[ops] {check.name}"
        if not check.ok and title not in open_issues:
            ops.append(OpenOps(title, (
                f"El chequeo **{check.name}** falló:\n\n```\n{check.detail}\n```\n\n"
                "Este issue se cierra solo cuando el chequeo se recupere. Para diagnosticar, pregúntale al operador."
            )))
        elif check.ok and title in open_issues:
            ops.append(CloseOps(open_issues[title], f"✅ El chequeo **{check.name}** se recuperó."))
    for name, expiry in sorted(expiries.items()):
        if expiry is None or (expiry - today).days > warn_days:
            continue
        title = f"[ops] Renovar {name} (vence {expiry.isoformat()})"
        if title not in open_issues:
            ops.append(OpenOps(title, (
                f"`{name}` vence el **{expiry.isoformat()}**. Renuévalo, actualiza `.env` "
                f"(incluida su fecha de vencimiento) y redespliega. Después cierra este issue."
            )))
    return ops


def run_checks(
    canvas_url: str, api_key: str, heartbeat_path: Path, tunnel_ready_url: str, disk_path: str, now: float
) -> list[Check]:
    checks: list[Check] = []
    try:
        resp = httpx.get(f"{canvas_url}/api/conversations/count", headers={"X-Session-API-Key": api_key}, timeout=15)
        checks.append(Check("canvas", resp.status_code == 200, f"HTTP {resp.status_code}"))
    except httpx.HTTPError as exc:
        checks.append(Check("canvas", False, f"{type(exc).__name__}: {exc}"))
    try:
        age = now - float(heartbeat_path.read_text().strip())
        checks.append(Check("dispatcher", age < HEARTBEAT_MAX_AGE, f"último ciclo hace {int(age)} s"))
    except FileNotFoundError:
        checks.append(Check("dispatcher", False, f"el latido {heartbeat_path} no existe"))
    except ValueError:
        checks.append(Check("dispatcher", False, f"el latido {heartbeat_path} es ilegible"))
    if tunnel_ready_url:
        try:
            resp = httpx.get(tunnel_ready_url, timeout=15)
            checks.append(Check("tunel", resp.status_code == 200, f"HTTP {resp.status_code}"))
        except httpx.HTTPError as exc:
            checks.append(Check("tunel", False, f"{type(exc).__name__}: {exc}"))
    usage = shutil.disk_usage(disk_path)
    used = usage.used / usage.total
    checks.append(Check("disco", used < DISK_MAX_USED, f"uso {used:.0%} de {usage.total // 2**30} GB"))
    return checks


class Watchdog:
    def __init__(self, github, repo: str, checker: Callable[[], list[Check]], expiries: Mapping[str, date | None],
                 today: Callable[[], date] = date.today):
        self.github, self.repo, self.checker, self.expiries, self.today = github, repo, checker, expiries, today

    def run_once(self) -> list[OpenOps | CloseOps]:
        checks = self.checker()
        try:
            open_issues = self.github.list_open_issue_titles(self.repo, "ops")
        except Exception:
            log.exception("No pude leer los issues ops; reintento en el próximo ciclo")
            return []
        ops = plan_ops(checks, self.expiries, open_issues, self.today())
        for op in ops:
            try:
                if isinstance(op, OpenOps):
                    self.github.create_issue(self.repo, op.title, op.body, ["ops"])
                else:
                    self.github.close_issue(self.repo, op.number, op.comment)
            except Exception:
                log.exception("Falló %s", op)
        for check in checks:
            log.info("%s %s %s", "OK " if check.ok else "MAL", check.name, check.detail)
        return ops


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = os.environ
    github = GitHubClient(env["GITHUB_TOKEN"], env.get("GITHUB_ORG", "maxiar-org"))
    checker = lambda: run_checks(  # noqa: E731
        env.get("CANVAS_URL", "http://canvas:8000"), env["CANVAS_API_KEY"],
        Path(env.get("HEARTBEAT_PATH", "/state/heartbeat")), env.get("TUNNEL_READY_URL", ""),
        env.get("DISK_PATH", "/"), time.time(),
    )
    expiries = {
        "GITHUB_TOKEN": parse_expiry(env.get("GITHUB_TOKEN_EXPIRES")),
        "CLAUDE_CODE_OAUTH_TOKEN": parse_expiry(env.get("CLAUDE_TOKEN_EXPIRES")),
    }
    watchdog = Watchdog(github, env.get("OPS_REPO", "ai-dev-team"), checker, expiries)
    interval = int(env.get("WATCHDOG_INTERVAL", "300"))
    while True:
        try:
            watchdog.run_once()
        except Exception:
            log.exception("Ciclo del watchdog fallido")
        time.sleep(interval)


if __name__ == "__main__":
    main()
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5:** commit con el mensaje `feat(watchdog): chequeos del stack con alertas en issues ops`.

---

### Tarea 3: Imagen del operador, `CLAUDE.md` y skills

**Archivos:**
- Crear: `operador/Dockerfile`, `operador/start.sh`, `CLAUDE.md`, `.claude/skills/estado/SKILL.md`, `.claude/skills/desplegar/SKILL.md`

- [ ] **Paso 1: `operador/Dockerfile`**

```dockerfile
# Operador del AI Dev Team: Claude Code con Remote Control, para operar el stack desde el celular.
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tmux python3 gnupg procps \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin gh \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

ARG UID=1001
ARG GID=1001
ARG DOCKER_GID=999
RUN groupadd -g ${GID} aidev && useradd -m -u ${UID} -g ${GID} -s /bin/bash aidev \
 && (getent group docker || groupadd -g ${DOCKER_GID} docker) && usermod -aG docker aidev
COPY --chmod=755 start.sh /usr/local/bin/operador-start
USER aidev
WORKDIR /opt/ai-dev-team
CMD ["/usr/local/bin/operador-start"]
```

- [ ] **Paso 2: `operador/start.sh`**

```bash
#!/bin/sh
# Mantiene una sesión tmux "operador" con Claude Code en Remote Control. Si claude termina, lo relanza.
set -e
git config --global --add safe.directory /opt/ai-dev-team
while true; do
  if ! tmux has-session -t operador 2>/dev/null; then
    tmux new-session -d -s operador -c /opt/ai-dev-team "claude --remote-control; sleep 5"
  fi
  sleep 30
done
```

- [ ] **Paso 3: `CLAUDE.md`** en la raíz de `ai-dev-team`, con:
  - **Rol:** "Eres el operador del AI Dev Team de Eduardo, y le respondes en español."
  - **Arquitectura:** Canvas como runtime ACP, dispatcher como orquestador, GitHub como fuente de verdad, el tablero Projects #1 y los roles dev, review, QA, docs y fix.
  - **Repos:** `REPOS` y `DOCS_ONLY_REPOS`.
  - **Comandos:**
    - `docker compose ps`, `logs`, `up -d --build <servicio>`;
    - `docker compose run --rm dispatcher report`;
    - `cd dispatcher && uv run pytest -q`.
  - **Diagnóstico:** issues `ops`, `state.json`, Canvas en `http://canvas:8000` con la clave de `.env`.
  - **Reglas:**
    1. No tocar `hermes` ni contenedores, volúmenes o redes fuera del proyecto Compose `ai-dev-team`.
    2. Nunca commitear `.env` ni mostrar secretos.
    3. Cambios al dispatcher solo con tests en verde, y en `main` solo si Eduardo lo pide explícitamente; si no, por PR.
    4. Antes de reiniciar el dispatcher, comprobar que no haya tareas activas o avisar.
    5. Seguir el estilo de los specs en `docs/superpowers/`.
  - **Referencias:** `docs/bitacora.md`, `pilot/REPORT.md` y los specs.

- [ ] **Paso 4: Skills**
  - **`.claude/skills/estado/SKILL.md`** (frontmatter con `name: estado` y `description: Resumen del estado del AI Dev Team y de cada proyecto, con acciones sugeridas para Eduardo`). El cuerpo indica:
    1. Recorrer cada repo de `REPOS` con `gh`: issues abiertos con sus labels, PRs abiertos con su estado de merge, review y checks, y los mergeados en las últimas 48 horas.
    2. Revisar el tablero (`gh project item-list 1 --owner maxiar-org`), `docker compose ps`, los issues `ops` abiertos, los logs recientes del dispatcher (`Inició`/`Terminó`) y `dispatcher report`.
    3. Responder con este formato: una tabla de estado por issue o PR, qué espera a Eduardo, las acciones sugeridas en orden (incluido el orden de merge si hay PRs que se pisan), y el consumo si cambió.
  - **`.claude/skills/desplegar/SKILL.md`** (frontmatter con `name: desplegar` y `description: Desplegar cambios del repo ai-dev-team en la mini-PC con verificación`). El cuerpo indica:
    1. `git pull`.
    2. `cd dispatcher && uv run pytest -q`; si no pasa, detenerse.
    3. Comprobar que no haya tareas activas (`docker compose exec dispatcher cat /state/state.json`).
    4. `docker compose up -d --build <servicios afectados>`.
    5. Verificar con `docker compose ps`, los logs sin errores y el latido reciente.
    6. Reportar.

- [ ] **Paso 5:** compilar la imagen de prueba en la Mac: `docker build -t ai-dev-team/operador ./operador && docker run --rm --entrypoint sh ai-dev-team/operador -c "claude --version && gh --version | head -1 && docker compose version && tmux -V"`. Resultado esperado: cuatro versiones.

- [ ] **Paso 6:** commit con el mensaje `feat(operador): imagen con Claude Code y Remote Control, CLAUDE.md y skills estado/desplegar`.

---

### Tarea 4: Compose con túnel, watchdog y operador

**Archivos:**
- Modificar: `docker-compose.yml`, `.env.example`, `README.md`

- [ ] **Paso 1:** en `docker-compose.yml`:
  - en el `environment` del `dispatcher`, agregar `HEARTBEAT_PATH: /state/heartbeat`;
  - agregar los servicios nuevos;
  - en `volumes:`, agregar `operador-home:`.

```yaml
  cloudflared:
    image: cloudflare/cloudflared:2026.9.1
    restart: unless-stopped
    command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN:?falta TUNNEL_TOKEN en .env}
    depends_on:
      - canvas

  watchdog:
    image: ai-dev-team-dispatcher
    restart: unless-stopped
    depends_on:
      - dispatcher
    entrypoint: ["python", "-m", "dispatcher.watchdog"]
    environment:
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_ORG: ${GITHUB_ORG:-maxiar-org}
      OPS_REPO: ai-dev-team
      CANVAS_URL: http://canvas:8000
      CANVAS_API_KEY: ${CANVAS_API_KEY}
      HEARTBEAT_PATH: /state/heartbeat
      TUNNEL_READY_URL: http://cloudflared:2000/ready
      DISK_PATH: /
      GITHUB_TOKEN_EXPIRES: ${GITHUB_TOKEN_EXPIRES:-}
      CLAUDE_TOKEN_EXPIRES: ${CLAUDE_TOKEN_EXPIRES:-}
    volumes:
      - dispatcher-state:/state:ro

  operador:
    build:
      context: ./operador
      args:
        UID: ${AIDEV_UID:-1001}
        GID: ${AIDEV_GID:-1001}
        DOCKER_GID: ${DOCKER_GID:-999}
    restart: unless-stopped
    init: true
    volumes:
      - operador-home:/home/aidev
      - .:/opt/ai-dev-team
      - /var/run/docker.sock:/var/run/docker.sock
```

  Verificar el tag de `cloudflared` con `docker pull cloudflare/cloudflared:2026.9.1`. Si no existe, usar el último tag estable publicado y anotarlo en el ledger.

- [ ] **Paso 2:** agregar a `.env.example`:
  - `TUNNEL_TOKEN=` (token del túnel `ai-dev-team` de Cloudflare Zero Trust);
  - `GITHUB_TOKEN_EXPIRES=` y `CLAUDE_TOKEN_EXPIRES=` (fechas ISO);
  - `DOCKER_GID=` (salida de `getent group docker | cut -d: -f3` en el host);
  - `AIDEV_UID=` y `AIDEV_GID=` (salida de `id -u aidev` e `id -g aidev` en el host), para que el operador escriba en el repo con el mismo dueño.

  Cada una con su comentario.

- [ ] **Paso 3: README.** Agregar una sección "Mini-PC y operador" con:
  - cómo entrar (`ssh ubuntu-labs`, `sudo -iu aidev`, `cd /opt/ai-dev-team`);
  - la URL `canvas.maxiar.dev`;
  - cómo conectarse al operador (app de Claude o claude.ai/code → sesión "operador");
  - cómo hacer login del operador la primera vez (`docker compose exec -it operador claude`);
  - qué hacer con un issue `ops`.

- [ ] **Paso 4: Validar el compose** con un `.env` de relleno: `docker compose --env-file <relleno> config --quiet && echo CONFIG_OK`. El relleno incluye `TUNNEL_TOKEN=x`.

- [ ] **Paso 5:** commit con el mensaje `feat(compose): túnel, watchdog y operador como servicios`.

---

### Tarea 5: Base en la mini-PC (como `root` por SSH)

- [ ] **Paso 1: Instalar Docker** desde el repositorio oficial:

```bash
ssh ubuntu-labs 'set -e
apt-get update -qq && apt-get install -y -qq ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version && docker compose version'
```

  Si el repo de Docker todavía no tiene paquetes para el codename de 26.04, usar el codename de la LTS anterior (`noble`) y anotarlo en el ledger.

- [ ] **Paso 2: Usuario y repo.**

```bash
ssh ubuntu-labs 'set -e
id aidev >/dev/null 2>&1 || useradd -m -s /bin/bash aidev
usermod -aG docker aidev
mkdir -p /opt/ai-dev-team && chown aidev:aidev /opt/ai-dev-team
sudo -iu aidev git clone https://github.com/maxiar-org/ai-dev-team.git /opt/ai-dev-team
sudo -iu aidev sh -c "cd /opt/ai-dev-team && git log --oneline | head -1"
getent group docker | cut -d: -f3; id -u aidev'
```

- [ ] **Paso 3: Copiar el `.env`** desde la Mac, ajustando `DOCKER_GID`:

```bash
scp .env ubuntu-labs:/opt/ai-dev-team/.env
ssh ubuntu-labs 'chown aidev:aidev /opt/ai-dev-team/.env && chmod 600 /opt/ai-dev-team/.env && ls -l /opt/ai-dev-team/.env'
```

  Agregar al `.env` de la mini-PC `DOCKER_GID`, `AIDEV_UID` y `AIDEV_GID` con los valores del paso 2.

- [ ] **Paso 4: Construir las imágenes** en la mini-PC: `ssh ubuntu-labs 'cd /opt/ai-dev-team && sudo -u aidev docker compose build'`. Tarda varios minutos por Flutter.

---

### Tarea 6: 👤 Cloudflare: dominio, túnel y Access (Eduardo)

- [ ] **Paso 1 👤:** comprar `maxiar.dev` en Cloudflare Registrar.
- [ ] **Paso 2 👤:** en Zero Trust → Networks → Tunnels:
  1. Crear un túnel `ai-dev-team` (tipo cloudflared) y copiar el **token** del comando de instalación (el valor después de `--token`).
  2. En **Public Hostname**, agregar `canvas.maxiar.dev` → `HTTP` → `canvas:8000`.
- [ ] **Paso 3 👤:** en Zero Trust → Access → Applications, crear una aplicación self-hosted para `canvas.maxiar.dev` con la política "Allow" para el email de Eduardo (login con código por email).
- [ ] **Paso 4:** pegar en el `.env` de la mini-PC `TUNNEL_TOKEN=<token>`, `GITHUB_TOKEN_EXPIRES=<fecha que muestra GitHub>` y `CLAUDE_TOKEN_EXPIRES=<fecha de creación + 1 año>`.

---

### Tarea 7: Corte y migración

- [ ] **Paso 1:** en la Mac, comprobar que no hay tareas activas (`docker compose exec dispatcher cat /state/state.json` muestra `"active": {}`) y luego `docker compose stop dispatcher`.
- [ ] **Paso 2: Exportar los volúmenes** en la Mac:

```bash
for v in canvas-state codex-home dispatcher-state; do
  docker run --rm -v ai-dev-team_$v:/v -v "$PWD/.superpowers:/out" alpine tar czf /out/$v.tgz -C /v .
done
scp .superpowers/*.tgz ubuntu-labs:/tmp/
```

- [ ] **Paso 3: Importar los volúmenes** en la mini-PC:

```bash
ssh ubuntu-labs 'cd /opt/ai-dev-team && for v in canvas-state codex-home dispatcher-state; do
  docker volume create ai-dev-team_$v >/dev/null
  docker run --rm -v ai-dev-team_$v:/v -v /tmp:/in alpine sh -c "cd /v && tar xzf /in/$v.tgz"
done; rm /tmp/*.tgz'
```

- [ ] **Paso 4: Levantar** en la mini-PC: `sudo -u aidev docker compose up -d`. Verificar:
  - `docker compose ps`: los 5 servicios en `running`;
  - `curl` a Canvas con la clave (`127.0.0.1:8000`) responde 200;
  - el latido se actualiza;
  - los logs del watchdog muestran `OK` en `canvas`, `dispatcher`, `tunel` y `disco`.
- [ ] **Paso 5:** prueba de ACP: correr `acp_smoke.py` (Claude y Codex) apuntando a la mini-PC por un túnel SSH (`ssh -L 8000:127.0.0.1:8000 ubuntu-labs`), o desde dentro del contenedor del dispatcher.
- [ ] **Paso 6:** en la Mac, `docker compose down` y `docker rm -f qr-app qr-tunnel`. Borrar los `.tgz` locales.

---

### Tarea 8: 👤 Login del operador y verificación final

- [ ] **Paso 1:** copiar la memoria al volumen del operador:

```bash
scp -r ~/.claude/projects/-Users-eduardo-ai-dev-team/memory ubuntu-labs:/tmp/memoria
ssh ubuntu-labs 'cd /opt/ai-dev-team && docker compose cp /tmp/memoria operador:/home/aidev/.claude/projects/-opt-ai-dev-team/memory && rm -rf /tmp/memoria'
```

  Si `docker compose cp` falla porque falta el directorio, crearlo antes con `docker compose exec operador mkdir -p /home/aidev/.claude/projects/-opt-ai-dev-team`.
- [ ] **Paso 2 👤:** login del operador.
  1. `ssh ubuntu-labs`, después `cd /opt/ai-dev-team && sudo -u aidev docker compose exec -it operador claude`, y completar el login por código con la **cuenta personal** de Eduardo.
  2. Salir y reiniciar el servicio: `docker compose restart operador`.
  3. Hacer login de `gh` para Eduardo dentro del operador: `docker compose exec -it operador gh auth login`.
- [ ] **Paso 3 👤:** desde la app de Claude o claude.ai/code, conectarse a la sesión "operador" y pedir `/estado`. Resultado esperado: el resumen del proyecto.
- [ ] **Paso 4:** **criterios de éxito** del spec, con la Mac apagada o al menos sin el stack corriendo:
  1. Un issue en `agent-playground` con `agent:dev` llega hasta el pedido de review.
  2. `canvas.maxiar.dev` abre desde el celular después del login de Access.
  3. `/estado` responde desde el celular.
  4. `docker compose stop dispatcher`: en menos de 10 minutos aparece `[ops] dispatcher`. Al hacer `start`, el issue se cierra solo.
  5. Con `reboot` de la VM, todo vuelve a levantarse solo: comprobarlo con `docker compose ps` y el watchdog en OK.
- [ ] **Paso 5:** registrar la etapa en `docs/bitacora.md` (resultados y problemas) y actualizar la memoria del operador.
