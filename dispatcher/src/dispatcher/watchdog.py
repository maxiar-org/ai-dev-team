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
