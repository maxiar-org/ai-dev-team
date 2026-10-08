from datetime import date

from dispatcher.models import Item
from dispatcher.view import AppInfo, PRInfo, Snapshot, View, build_view, merge_order, render
from dispatcher.watchdog import Check

NOW = 1_791_500_000.0  # 2026-10-08 aprox.


def pr(n, *labels, body="", ref=None, clean=True, ci="success", files=()):
    return PRInfo("qr", n, f"PR {n}", f"https://github.com/o/qr/pull/{n}", frozenset(labels), body,
                  ref or "feat/x", "clean" if clean else "dirty", ci, tuple(files))


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


def test_render_sections_and_empty_state():
    html = render(View(updated=NOW))
    for title in ("Qué espera de ti", "Trabajo en curso", "Despliegues", "Salud y consumo", "Resumen del operador"):
        assert title in html
    assert "Nada pendiente" in html and 'http-equiv="refresh"' in html and "hace __EDAD__ s" in html


def test_render_escapes_external_text():
    v = View(updated=NOW, waiting=[{"repo": "qr", "number": 1, "title": "<script>x</script>", "url": "https://g/1", "ci": "success",
                                    "clean": True, "preview": None, "issue": None, "warnings": []}])
    html = render(v)
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


def test_render_shows_source_errors():
    assert "sin datos" in render(View(updated=NOW, errors={"coolify": "ConnectError"}))
