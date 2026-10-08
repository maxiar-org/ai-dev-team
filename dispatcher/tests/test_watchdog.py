from datetime import date

import httpx
import respx

from dispatcher.watchdog import Check, CloseOps, OpenOps, Watchdog, parse_expiry, plan_ops, run_checks

TODAY = date(2026, 10, 7)


def test_failing_check_opens_one_issue_only():
    checks = [Check("canvas", False, "HTTP 502"), Check("dispatcher", True)]
    first = plan_ops(checks, {}, {}, TODAY)
    assert first == [OpenOps("[ops] canvas", first[0].body)] and "HTTP 502" in first[0].body
    assert plan_ops(checks, {}, {"[ops] canvas": 12}, TODAY) == []


def test_recovered_check_closes_its_issue():
    [op] = plan_ops([Check("canvas", True)], {}, {"[ops] canvas": 12}, TODAY)
    assert isinstance(op, CloseOps) and op.number == 12 and "recuperó" in op.comment


def test_expiry_warning_once_within_14_days():
    exp = {"GITHUB_TOKEN": date(2026, 10, 20), "CLAUDE_CODE_OAUTH_TOKEN": date(2027, 10, 4)}
    [op] = plan_ops([], exp, {}, TODAY)
    assert op.title == "[ops] Renovar GITHUB_TOKEN (vence 2026-10-20)"
    assert plan_ops([], exp, {op.title: 5}, TODAY) == []


def test_bad_expiry_dates_are_ignored():
    assert parse_expiry("") is None
    assert parse_expiry("no-es-fecha") is None
    assert parse_expiry("2027-01-01") == date(2027, 1, 1)


def test_missing_or_garbage_heartbeat_fails_cleanly(tmp_path):
    hb = tmp_path / "heartbeat"
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert not checks["dispatcher"].ok and "no existe" in checks["dispatcher"].detail
        hb.write_text("basura")
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert not checks["dispatcher"].ok
        hb.write_text("900.0")
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
        assert checks["dispatcher"].ok and checks["canvas"].ok and checks["disco"].ok
        assert "tunel" not in checks


def test_canvas_and_tunnel_failures(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").mock(side_effect=httpx.ConnectError("refused"))
        respx.get("http://cloudflared:2000/ready").respond(503)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "http://cloudflared:2000/ready", str(tmp_path), now=1000.0)}
    assert not checks["canvas"].ok and "refused" in checks["canvas"].detail
    assert not checks["tunel"].ok and "503" in checks["tunel"].detail


class FakeGH:
    def __init__(self, fail=False):
        self.created, self.closed, self.fail = [], [], fail

    def list_open_issue_titles(self, repo, label):
        if self.fail:
            raise httpx.ConnectError("sin red")
        return {}

    def create_issue(self, repo, title, body, labels):
        self.created.append(title)

    def close_issue(self, repo, number, comment):
        self.closed.append(number)


def test_github_errors_do_not_crash_watchdog_cycle():
    wd = Watchdog(FakeGH(fail=True), "ai-dev-team", lambda: [Check("canvas", False, "x")], {}, today=lambda: TODAY)
    assert wd.run_once() == []


def test_watchdog_needs_two_consecutive_failures_before_opening():
    gh = FakeGH()
    results = iter([[Check("canvas", False, "x")], [Check("canvas", True)], [Check("canvas", False, "x")], [Check("canvas", False, "x")]])
    wd = Watchdog(gh, "ai-dev-team", lambda: next(results), {}, today=lambda: TODAY)
    wd.run_once()  # primera falla: puede ser un arranque, no alerta
    wd.run_once()  # se recuperó
    wd.run_once()  # falla otra vez: racha 1
    assert gh.created == []
    wd.run_once()  # segunda falla seguida: alerta
    assert gh.created == ["[ops] canvas"]


def test_check_errors_do_not_abort_other_checks(tmp_path):
    hb_dir = tmp_path / "soy-un-directorio"
    hb_dir.mkdir()
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb_dir, "", str(tmp_path / "no-existe"), now=1000.0)}
    assert checks["canvas"].ok
    assert not checks["dispatcher"].ok and not checks["disco"].ok


def test_future_or_infinite_heartbeat_fails(tmp_path):
    hb = tmp_path / "hb"
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        for value in ("inf", "5000.0"):
            hb.write_text(value)
            checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
            assert not checks["dispatcher"].ok, value


def test_coolify_check_reports_health(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        respx.get("http://coolify:8080/api/health").respond(502)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0,
                                                coolify_health_url="http://coolify:8080/api/health")}
    assert not checks["coolify"].ok and "502" in checks["coolify"].detail


def test_coolify_check_absent_when_not_configured(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        checks = {c.name for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
    assert "coolify" not in checks
