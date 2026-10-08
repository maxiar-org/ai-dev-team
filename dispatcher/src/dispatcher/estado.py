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
from .view import AGE_MARK, PRInfo, Snapshot, build_view, render
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
    """Último HTML generado; la antigüedad se completa en cada pedido."""

    def __init__(self) -> None:
        self.html = "<!doctype html><meta charset=utf-8><p>Cargando…</p>"
        self.generated_at = time.time()

    def update(self, html: str, generated_at: float) -> None:
        self.html, self.generated_at = html, generated_at

    def body(self, now: float) -> str:
        return self.html.replace(AGE_MARK, str(max(0, int(now - self.generated_at))))


def serve(page: Page, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"ok" if self.path == "/health" else page.body(time.time()).encode()
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
                now = time.time()
                page.update(render(build_view(collector.collect(now))), now)
            except Exception:
                log.exception("No pude armar la vista")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    serve(page, int(env.get("ESTADO_PORT", "8090"))).serve_forever()


if __name__ == "__main__":
    main()
