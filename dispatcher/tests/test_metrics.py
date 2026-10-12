from datetime import datetime, timedelta, timezone

from dispatcher.metrics import FIELDS, LimitLog, MetricsLog, summarize
from dispatcher.models import ActiveTask, ConvInfo

T0 = datetime(2026, 10, 3, 22, 0, tzinfo=timezone.utc)


def test_append_writes_header_once_and_token_columns(tmp_path):
    log = MetricsLog(tmp_path / "m.csv")
    task = ActiveTask("qr", 3, "issue", "dev", "codex", "label", "c1", 1_000.0, "/p")
    log.append(task, "finished", "pr_abierto", ConvInfo("c1", "finished", 1000, 200, 300, 0.75), 1_000.0 + 90 * 60)
    log.append(task, "timeout", "needs_human", None, 1_000.0 + 60)
    rows = log.read()
    assert len(rows) == 2
    assert (rows[0]["duracion_min"], rows[0]["tokens_entrada"], rows[0]["costo_estimado_usd"]) == ("90.0", "1000", "0.7500")
    assert (rows[1]["estado_final"], rows[1]["tokens_entrada"]) == ("timeout", "0")
    assert (tmp_path / "m.csv").read_text().count("repo,numero") == 1


def row(**overrides):
    base = {field: "0" for field in FIELDS}
    base.update(repo="qr", numero="3", tipo="issue", rol="dev", motor="codex", disparador="label",
                inicio=T0.isoformat(), duracion_min="10.0", resultado="pr_abierto", costo_estimado_usd="0.10")
    base.update(overrides)
    return base


def test_summarize_groups_by_engine_result_and_window():
    h = lambda hours: (T0 + timedelta(hours=hours)).isoformat()
    rows = [
        row(inicio=h(0), tokens_entrada="100"),
        row(inicio=h(1), tokens_entrada="50"),
        row(inicio=h(7)),
        row(motor="claude", rol="review", tipo="pr", numero="7", resultado="aprobado", inicio=h(2)),
    ]
    md = summarize(rows, {("qr", 7): True})
    assert "| codex | 3 | 2 | 10.0 | 150 | 0 | 0.30 |" in md
    assert "| claude | 1 | 1 | 10.0 | 0 | 0 | 0.10 |" in md
    assert "| aprobado | 1 |" in md and "| pr_abierto | 3 |" in md
    assert "| qr | #7 | sí |" in md


def active_task():
    return ActiveTask("qr", 1, "issue", "dev", "codex", "label", "c2", 0.0, "/w", slot="codex-senior")


def test_old_header_is_upgraded_without_misaligning_rows(tmp_path):
    p = tmp_path / "metrics.csv"
    old = ",".join(FIELDS[:-2])
    p.write_text(old + "\nqr,1,issue,dev,codex,label,a,b,1.0,finished,pr_abierto,0,0,0,0.0000,c1\n")
    MetricsLog(p).append(active_task(), "finished", "pr_abierto", None, 100.0, images=2)
    rows = MetricsLog(p).read()
    assert rows[0]["conversacion"] == "c1" and rows[0]["puesto"] == ""
    assert rows[1]["puesto"] == "codex-senior" and rows[1]["imagenes_gemini"] == "2"


def test_limit_log_appends(tmp_path):
    log = LimitLog(tmp_path / "limits.csv")
    log.append("codex-senior", "codex", 10.0, 20.0, "qr#1", "x" * 500)
    [row] = log.read()
    assert row["puesto"] == "codex-senior" and len(row["mensaje"]) == 200
