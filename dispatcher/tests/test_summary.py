from dispatcher.summary import NOTICE_MARK, md_to_html, period_data, render_summary
from dispatcher.view import AppInfo, View, render
from dispatcher.watchdog import Check

NOW = 1_791_500_000.0


def test_md_to_html_is_safe():
    html = md_to_html('## Qué pasó\n- <script>x</script> **ok**\n- [malo](javascript:alert(1)) [bien](https://github.com/o/r/pull/1)\n'
                      '1. [q](https://x.dev/"onmouseover="a)')
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>ok</b>" in html
    assert 'href="javascript' not in html and '<a href="https://github.com/o/r/pull/1">bien</a>' in html
    assert '"onmouseover="' not in html and "<h3>Qué pasó</h3>" in html and "<ol>" in html and "<ul>" in html


def test_period_data_filters_metrics_since_and_compacts_view():
    view = View(updated=NOW, waiting=[{"repo": "qr", "number": 1, "title": "t", "url": "u", "ci": "success", "clean": True,
                                       "preview": None, "issue": 3, "issue_url": None, "warnings": []}],
                apps=[AppInfo("qr", "maxiar-org/qr", "https://qr.maxiar.dev", "running")], health=[Check("canvas", True, "HTTP 200")])
    rows = [{"repo": "qr", "numero": "3", "rol": "dev", "motor": "codex", "resultado": "pr_abierto", "duracion_min": "5.0",
             "fin": "2026-10-08T23:00:00+00:00"},
            {"repo": "qr", "numero": "2", "rol": "dev", "motor": "codex", "resultado": "pr_abierto", "duracion_min": "5.0",
             "fin": "2026-10-07T10:00:00+00:00"},
            {"repo": "qr", "fin": None}]
    d = period_data(view, "2026-10-08T00:00:00Z", NOW, merged=[{"number": 23}], closed=[], ops=[], metrics=rows)
    assert d["desde"] == "2026-10-08T00:00:00Z" and d["mergeados"] == [{"number": 23}]
    assert d["tareas"] == [{"repo": "qr", "numero": "3", "rol": "dev", "motor": "codex", "resultado": "pr_abierto", "minutos": "5.0"}]
    assert d["espera_a_eduardo"][0]["number"] == 1 and d["salud"] == [{"name": "canvas", "ok": True, "detail": "HTTP 200"}]
    assert d["despliegues"] == [{"name": "qr", "url": "https://qr.maxiar.dev", "status": "running", "last_deploy": None}]


def test_render_summary_states():
    idle = {"status": "idle", "since": "x", "started_at": None, "error": None,
            "last": {"generated_at": "2026-10-09T00:14:00Z", "since": "2026-10-08T00:14:00Z", "markdown": "## Qué pasó\n- nada"}}
    html = render_summary(idle, None, NOW)
    assert "Pedir resumen" in html and "<h3>Qué pasó</h3>" in html and "08/10 21:14" in html and NOTICE_MARK in html
    running = dict(idle, status="running", started_at=NOW - 42)
    html = render_summary(running, None, NOW)
    assert "generando… hace 42 s" in html and "Pedir resumen" not in html
    failed = dict(idle, error="TimeoutExpired: 300 s")
    assert "el último pedido falló: TimeoutExpired" in render_summary(failed, None, NOW)
    assert "sin datos (ConnectError)" in render_summary(None, "ConnectError", NOW)
    assert "Todavía no hay resúmenes" in render_summary(dict(idle, last=None), None, NOW)


def test_page_reloads_faster_while_generating():
    v = View(updated=NOW, summary={"status": "running", "since": "x", "started_at": NOW, "last": None, "error": None})
    assert 'content="10"' in render(v)
    assert 'content="60"' in render(View(updated=NOW))
