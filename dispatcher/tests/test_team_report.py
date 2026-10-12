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
