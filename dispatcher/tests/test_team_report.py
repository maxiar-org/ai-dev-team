from dispatcher.metrics import iso
from dispatcher.models import Slot
from dispatcher.team_report import decision_alerts, slot_stats

DAY = 86400.0
NOW = 1_800_000_000.0
SLOTS = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"))


def m(slot, rol, numero, start, minutes, imgs=0, repo="nikito"):
    return {"repo": repo, "numero": str(numero), "rol": rol, "puesto": slot, "inicio": iso(start),
            "duracion_min": str(minutes), "imagenes_gemini": str(imgs), "motor": slot.split("-")[0]}


def lim(slot, detected, hours):
    return {"puesto": slot, "detectado": iso(detected), "hasta": iso(detected + hours * 3600)}


def test_slot_stats_counts_minutes_rework_cost_and_exhaustion():
    rows = [m("codex-senior", "dev", 3, NOW - 3600, 30), m("codex-senior", "fix", 3, NOW - 1800, 10),
            m("codex-senior", "qa", 3, NOW - 900, 5, imgs=2), m("claude-senior", "dev", 4, NOW - 10 * DAY, 60)]
    stats = slot_stats(rows, [lim("codex-senior", NOW - 7200, 1)], SLOTS, {"codex-senior": 300.0}, 0.04, NOW, DAY)
    s = stats["codex-senior"]
    assert (s.tasks, s.minutes, s.limit_hits) == (3, 45.0, 1)
    assert round(s.utilization, 3) == round(45 / 1440, 3)
    assert s.exhausted_hours == 1.0
    assert s.rework_per_issue == 2.0  # fix + qa sobre un issue
    assert round(s.cost_usd, 2) == round(300 / 30 + 2 * 0.04, 2)  # fijo mensual prorrateado a 1 día + imágenes
    assert stats["claude-senior"].tasks == 0


def test_alert_when_slot_exhausted_over_2h_on_3_of_last_5_days():
    limits = [lim("codex-senior", NOW - d * DAY - 4 * 3600, 3) for d in (0, 1, 3)]
    alerts = decision_alerts(limits, [], SLOTS, NOW)
    assert any("codex-senior" in a and "subir" in a for a in alerts)


def test_alert_when_slot_under_20_percent_in_7_days():
    alerts = decision_alerts([], [m("claude-senior", "dev", 1, NOW - DAY, 60)], SLOTS, NOW)
    assert any("claude-senior" in a and "bajar" in a for a in alerts)


def test_alert_on_high_rework():
    rows = [m("codex-senior", r, 1, NOW - 3600, 5) for r in ("dev", "fix", "qa", "fix", "qa", "fix")]
    rows += [m("codex-senior", "dev", 2, NOW - 3600, 600)]
    assert any("retrabajo" in a for a in decision_alerts([], rows, SLOTS, NOW))


from datetime import datetime
from zoneinfo import ZoneInfo

from dispatcher.team_report import (UNASSIGNED, clean_limits, clean_metrics, daily_hours, flow_times, hour_strip,
                                    project_costs, rework_per_issue)

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


def test_project_costs_split_fixed_by_minutes_and_keep_unassigned():
    costs = {"codex-senior": 300.0, "claude-senior": 60.0}
    rows = [m("codex-senior", "dev", 1, NOW - 3600, 30, repo="nikito"), m("codex-senior", "qa", 2, NOW - 1800, 10, imgs=2, repo="qr")]
    pc = project_costs(rows, SLOTS, costs, 0.04, NOW, DAY)
    assert round(pc["nikito"]["cost"], 6) == round(10.0 * 30 / 40, 6) and pc["nikito"]["minutes"] == 30.0
    assert round(pc["qr"]["cost"], 6) == round(10.0 * 10 / 40 + 0.08, 6) and pc["qr"]["images"] == 2
    assert round(pc[UNASSIGNED]["cost"], 6) == 2.0  # claude-senior no trabajó: 60 USD al mes son 2 por día
    total = sum(s.cost_usd for s in slot_stats(rows, [], SLOTS, costs, 0.04, NOW, DAY).values())
    assert round(sum(p["cost"] for p in pc.values()), 6) == round(total, 6)
    assert project_costs([], SLOTS, {}, 0.04, NOW, DAY) == {}


def test_rework_per_issue_is_public():
    assert rework_per_issue([m("codex-senior", r, 1, NOW, 5) for r in ("dev", "fix", "qa")]) == 2.0
