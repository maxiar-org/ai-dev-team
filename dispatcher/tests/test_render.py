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
                    expiries={"GITHUB_TOKEN": date(2026, 10, 30)}, ops=[(3, "[ops] canvas", "https://x/3")], tz="UTC",
                    slot_costs={"claude-senior": 100.0}, health_links={"canvas": "https://canvas.maxiar.dev"},
                    repo_projects={"qr": [{"title": "QR Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/2"}]})
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
    assert "Decidir" in html and "¿Qué medida?" in html and "Revisar y mergear" in html and "hace 46 h" in html
    assert "[ops] canvas" in html and "vence en" in html


def test_render_links_everything_and_jumps_to_summary():
    html = render(full_view())
    for href in ("https://github.com/maxiar-org/qr", "https://github.com/orgs/maxiar-org/projects/2", "https://qr.maxiar.dev",
                 "https://canvas.maxiar.dev", "#resumen"):
        assert f'href="{href}"' in html
    assert 'id="resumen"' in html and "Ir al resumen" in html
    assert "Costo por proyecto" in html and "sin asignar" in html


def test_empty_view_says_nothing_pending():
    v = build_view(Snapshot(now=NOW))
    for b in v.budget.values():  # sin datos, la regla de uso bajo de la fase 5a ya avisa: se vacían para probar el texto
        b["alerts"] = []
    html = render(v)
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
