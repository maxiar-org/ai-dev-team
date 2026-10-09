"""Servicio de la vista de estado: recolecta cada 60 s y sirve el HTML (python -m dispatcher.estado)."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from html import escape
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .coolify import CoolifyClient
from .github import GitHubClient
from .metrics import MetricsLog
from .models import LABEL_HUMAN
from .resumen_client import ResumenClient
from .summary import NOTICE_MARK, period_data
from .view import AGE_MARK, PRInfo, Snapshot, awaits_human, build_view, render
from .watchdog import parse_expiry, run_checks

log = logging.getLogger("estado")


class Collector:
    def __init__(self, github, coolify, repos, org, bot_login, ops_repo, state_path: Path, metrics_path: Path,
                 checker: Callable[[], list], expiries: dict, resumen=None):
        self.github, self.coolify, self.repos, self.org = github, coolify, repos, org
        self.bot_login, self.ops_repo = bot_login, ops_repo
        self.state_path, self.metrics_path, self.checker, self.expiries = state_path, metrics_path, checker, expiries
        self.resumen = resumen

    def period(self, since: str) -> tuple[list, list, list, list]:
        org = self.org
        merged = self.github.search_since(f"org:{org} is:pr is:merged merged:>={since}")
        closed = self.github.search_since(f"org:{org} is:issue is:closed closed:>={since}")
        ops = self.github.search_since(f"repo:{org}/{self.ops_repo} label:ops updated:>={since}")
        return merged, closed, ops, MetricsLog(self.metrics_path).read()

    def _collect_repo(self, repo: str, snap: Snapshot) -> None:
        prs, issues, notes = [], [], {}
        for it in self.github.list_open_items(repo):
            if it.kind == "pr":
                url = f"https://github.com/{self.org}/{repo}/pull/{it.number}"
                if awaits_human(it.labels):  # el detalle (3 llamadas) solo para los que pueden esperar a Eduardo
                    d = self.github.pr_details(repo, it.number)
                    prs.append(PRInfo(repo, it.number, it.title, url, it.labels, it.body, d["head_ref"],
                                      d["mergeable_state"], d["ci"], d["files"]))
                else:
                    prs.append(PRInfo(repo, it.number, it.title, url, it.labels, it.body, it.head_ref or ""))
            else:
                issues.append(it)
            if LABEL_HUMAN in it.labels:
                note = self.github.last_comment_by(repo, it.number, self.bot_login)
                if note:
                    notes[f"{repo}#{it.number}"] = note
        snap.prs.extend(prs)
        snap.issues.extend(issues)
        snap.human_notes.update(notes)

    def collect(self, now: float) -> Snapshot:
        snap = Snapshot(now=now, org=self.org, expiries=self.expiries)

        def section(name: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except Exception as exc:  # una fuente caída nunca tira la página
                log.warning("Sección %s sin datos: %s", name, exc)
                snap.errors[name] = f"{type(exc).__name__}: {exc}"[:200]

        def github() -> None:
            failed = []
            for repo in self.repos:
                try:  # un repo con error no se lleva a los demás
                    self._collect_repo(repo, snap)
                except Exception as exc:
                    log.warning("Repo %s sin datos: %s", repo, exc)
                    failed.append(f"{repo}: {type(exc).__name__}")
            titles = self.github.list_open_issue_titles(self.ops_repo, "ops")
            snap.ops = [(n, t, f"https://github.com/{self.org}/{self.ops_repo}/issues/{n}") for t, n in sorted(titles.items(), key=lambda x: x[1])]
            if failed:
                raise RuntimeError(", ".join(failed))

        def dispatcher() -> None:
            if self.state_path.exists():
                snap.active = json.loads(self.state_path.read_text()).get("active", {})

        def coolify() -> None:
            if self.coolify is not None:
                snap.apps = self.coolify.apps()

        def salud() -> None:
            snap.checks = self.checker()
            snap.metrics = MetricsLog(self.metrics_path).read()

        def resumen() -> None:
            if self.resumen is not None:
                snap.summary = self.resumen.status()

        section("github", github)
        section("dispatcher", dispatcher)
        section("coolify", coolify)
        section("salud", salud)
        section("resumen", resumen)
        return snap


class Page:
    """Último HTML generado (y su vista); la antigüedad y el aviso se completan en cada pedido."""

    def __init__(self) -> None:
        self.html = "<!doctype html><meta charset=utf-8><p>Cargando…</p>"
        self.generated_at = time.time()
        self.view = None
        self.lock = threading.Lock()  # el hilo de recolección y los pedidos HTTP la actualizan

    def update(self, html: str, generated_at: float, view=None) -> None:
        with self.lock:
            self.html, self.generated_at = html, generated_at
            if view is not None:
                self.view = view

    def body(self, now: float, notice: str | None = None) -> str:
        aviso = f'<p class="bad">⚠️ {escape(notice[:300])}</p>' if notice else ""
        return self.html.replace(AGE_MARK, str(max(0, int(now - self.generated_at)))).replace(NOTICE_MARK, aviso)


def refresh(page: Page, collector, now: float) -> None:
    """Regenera la página; si algo falla, muestra el error en lugar de dejar la versión vieja congelada."""
    try:
        view = build_view(collector.collect(now))
        page.update(render(view), now, view)
    except Exception as exc:
        log.exception("No pude armar la vista")
        with page.lock:
            page.view = None  # que refresh_summary no vuelva a dibujar la vista vieja encima del error
        page.update('<!doctype html><meta charset=utf-8><meta name="viewport" content="width=device-width">'
                    '<meta http-equiv="refresh" content="60"><p>⚠️ No pude armar la vista: '
                    f"{escape(type(exc).__name__)}: {escape(str(exc)[:200])}</p>", now)


def refresh_summary(page: Page, resumen, now: float) -> None:
    """Actualiza solo el estado del resumen y re-renderiza (mientras genera, la página se recarga cada 10 s)."""
    view = page.view
    if view is None or resumen is None:
        return
    try:
        view.summary = resumen.status()
        view.errors.pop("resumen", None)
    except Exception as exc:
        view.errors["resumen"] = f"{type(exc).__name__}: {exc}"[:200]
    html = render(view)
    with page.lock:
        if page.view is view:  # si la recolección ya trajo una vista nueva, no se pisa
            page.html = html


def _same_origin(origin: str | None, expected: str) -> bool:
    """Origin (o Referer) con el mismo esquema y host exactos; nada de prefijos."""
    if not origin or not expected:
        return False
    got, want = urlparse(origin), urlparse(expected)
    return (got.scheme, got.netloc) == (want.scheme, want.netloc)


def handle_post(page: Page, collector, resumen, origin: str | None, expected_origin: str, now: float) -> tuple[int, str]:
    if not _same_origin(origin, expected_origin):
        return 403, ""
    if resumen is None or page.view is None:
        return 303, "/?error=" + quote("El resumen no está configurado o la vista todavía no cargó")
    try:
        st = resumen.status()
        if st.get("status") != "running":
            since = st["since"]
            resumen.request(period_data(page.view, since, now, *collector.period(since)))
    except Exception as exc:
        log.warning("No pude pedir el resumen: %s", exc)
        return 303, "/?error=" + quote(f"No pude pedir el resumen: {type(exc).__name__}: {exc}"[:300])
    refresh_summary(page, resumen, now)
    return 303, "/"


def serve(page: Page, port: int, collector=None, resumen=None, expected_origin: str = "",
          host: str = "0.0.0.0") -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", location: str = "") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, b"ok")
            if page.view is not None and (page.view.summary or {}).get("status") == "running":
                refresh_summary(page, resumen, time.time())
            notice = parse_qs(url.query).get("error", [None])[0]
            self._send(200, page.body(time.time(), notice).encode(), "text/html; charset=utf-8")

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/resumen":
                return self._send(404, b"no encontrado")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if 0 < length <= 10_000:
                self.rfile.read(length)
            origin = self.headers.get("Origin") or self.headers.get("Referer")
            code, location = handle_post(page, collector, resumen, origin, expected_origin, time.time())
            if code == 303:
                return self._send(303, location=location)
            self._send(code, "origen no permitido".encode())

        def log_message(self, *args):  # sin ruido en los logs
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = os.environ
    org = env.get("GITHUB_ORG", "maxiar-org")
    github = GitHubClient(env["GITHUB_TOKEN"], org)
    resumen = ResumenClient(env["RESUMEN_URL"], env["RESUMEN_TOKEN"]) if env.get("RESUMEN_TOKEN") else None
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
        resumen=resumen,
    )
    page = Page()
    interval = int(env.get("ESTADO_INTERVAL", "60"))

    def loop() -> None:
        while True:
            refresh(page, collector, time.time())
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    # Solo en la red `publico` (estado + cloudflared): el alias estado-publico resuelve a esa IP, así los agentes
    # de Canvas (en `default`) no llegan ni a la página ni al botón.
    host = socket.gethostbyname(env.get("ESTADO_HOST", "estado-publico"))
    serve(page, int(env.get("ESTADO_PORT", "8090")), collector, resumen,
          env.get("ESTADO_ORIGIN", "https://estado.maxiar.dev"), host).serve_forever()


if __name__ == "__main__":
    main()
