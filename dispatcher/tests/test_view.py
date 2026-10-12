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
    assert v.human == [{"repo": "qr", "number": 8, "title": "Issue 8", "url": "https://github.com/maxiar-org/qr/issues/8", "note": "¿Qué medida usa?",
                       "age": None, "kind": "issue"}]
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


# --- Arreglos de la revisión final ---

def test_null_fields_from_coolify_do_not_break_view():
    app = AppInfo("img", "", "", "")
    html = render(build_view(Snapshot(now=NOW, apps=[app])))
    assert "img" in html


def test_usage_skips_truncated_metric_rows():
    rows = [{"motor": None, "inicio": None, "duracion_min": None}, {"motor": "codex"}]
    assert build_view(Snapshot(now=NOW, metrics=rows)).usage == []


def test_github_down_never_says_nothing_pending():
    html = render(build_view(Snapshot(now=NOW, errors={"github": "ConnectError"})))
    assert "Nada pendiente" not in html and html.count("sin datos") == 2


def test_pr_of_issue_still_in_dev_is_not_waiting():
    snap = Snapshot(now=NOW, issues=[issue(3, "agent:working")], prs=[pr(10, ref="agent/3-x"), pr(11, ref="agent/4-y")],
                    active={"qr#4": {"role": "dev", "engine": "codex", "started_at": NOW}})
    assert build_view(snap).waiting == []


def test_only_dirty_counts_as_conflict():
    snap = Snapshot(now=NOW, prs=[pr(10)])
    for state, clean in (("blocked", True), ("unknown", True), ("dirty", False)):
        p = PRInfo("qr", 10, "t", "u", frozenset(), "", "feat/x", state, "success")
        assert build_view(Snapshot(now=NOW, prs=[p])).waiting[0]["clean"] is clean


def test_merge_order_and_overlap_are_per_repo():
    a = PRInfo("qr", 20, "a", "u", frozenset(), "Closes #5", "", "clean", "success", ("README.md",))
    b = PRInfo("lab", 21, "b", "u", frozenset(), "Closes #4", "", "clean", "success", ("README.md",))
    issues = [Item("qr", 5, "issue", "", "Depende de #4", frozenset()), Item("lab", 4, "issue", "", "", frozenset())]
    assert [p.number for p in merge_order([a, b], issues)] == [20, 21]
    assert all(w["warnings"] == [] for w in build_view(Snapshot(now=NOW, prs=[a, b], issues=issues)).waiting)


def test_render_shows_linked_issue_and_dispatcher_error():
    v = build_view(Snapshot(now=NOW, prs=[pr(10, ref="agent/3-x")], issues=[issue(3)], errors={"dispatcher": "JSONDecodeError"}))
    html = render(v)
    assert "https://github.com/maxiar-org/qr/issues/3" in html and "sin datos (JSONDecodeError)" in html


def test_preview_template_with_domain_is_skipped():
    app = AppInfo("x", "maxiar-org/qr", "https://qr.maxiar.dev", "running", preview_template="{{pr_id}}.{{domain}}", preview_prs=(10,))
    assert build_view(Snapshot(now=NOW, prs=[pr(10)], apps=[app])).previews == []


def test_app_status_traduce_estado_de_coolify():
    from dispatcher.view import _app_status
    assert _app_status("running:unknown") == ("ok", "Corriendo (sin healthcheck)")
    assert _app_status("running:healthy") == ("ok", "Corriendo (sana)")
    assert _app_status("running:unhealthy") == ("bad", "Corriendo (con fallas)")
    assert _app_status("exited:unhealthy") == ("bad", "Detenida (con fallas)")
    assert _app_status("running") == ("ok", "Corriendo")
    assert _app_status("") == ("bad", "desconocido")


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
    assert len(cards["codex-senior"]["cells"]) == 24 and cards["codex-senior"]["cells"][22]["state"] == "trabajando"
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
    assert p["lab"] == {"repo": "lab", "url": "https://github.com/maxiar-org/lab", "views": [], "sites": [], "epic": None,
                        "counts": dict.fromkeys(COLUMNS, 0), "items": []}


def test_projects_carry_repo_views_and_sites():
    app = AppInfo("qr-generator", "maxiar-org/qr", "https://qr.maxiar.dev", "running:healthy")
    other = AppInfo("otra", "maxiar-org/otra", "https://otra.maxiar.dev", "running:healthy")
    snap = Snapshot(now=NOW, org="maxiar-org", repos=("qr",), apps=[app, other],
                    repo_projects={"qr": [{"title": "QR Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/2"}]},
                    health_links={"canvas": "https://canvas.x"})
    v = build_view(snap)
    p = v.projects[0]
    assert p["url"] == "https://github.com/maxiar-org/qr"
    assert p["views"] == [{"title": "QR Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/2"}]
    assert p["sites"] == [{"name": "qr-generator", "url": "https://qr.maxiar.dev", "status": "running:healthy"}]
    assert v.health_links == {"canvas": "https://canvas.x"}


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
    assert [p["repo"] for p in b7["by_project"]] == ["qr", "sin asignar"]
    assert round(sum(p["cost"] for p in b7["by_project"]), 6) == round(b7["cost"], 6)
    assert b7["by_project"][0]["closed"] == 1 and b7["by_project"][0]["cost_per_issue"] == b7["by_project"][0]["cost"]


def test_budget_without_costs_or_closed_issues():
    b = build_view(Snapshot(now=NOW)).budget["7"]
    assert b["cost"] == 0 and b["closed"] == 0 and b["cost_per_issue"] is None and b["by_project"] == []
    assert [e["slot"] for e in b["exhausted"]] == ["claude", "codex"]


def test_waiting_and_human_carry_age():
    p = PRInfo("qr", 10, "t", "u", frozenset(), "", "feat/x", "clean", "success", (), ts(3))
    h = Item("qr", 8, "issue", "Duda", "", frozenset({"needs:human"}), updated_at=ts(1))
    v = build_view(Snapshot(now=NOW, prs=[p], issues=[h]))
    assert v.waiting[0]["age"] == 3 * 3600 and v.human[0]["age"] == 3600 and v.human[0]["kind"] == "issue"
    assert build_view(Snapshot(now=NOW, prs=[pr(11)])).waiting[0]["age"] is None
