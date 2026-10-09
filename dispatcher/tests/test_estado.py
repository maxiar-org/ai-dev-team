from pathlib import Path

from dispatcher.estado import Collector, Page, handle_post, refresh_summary
from dispatcher.models import Item
from dispatcher.view import Snapshot, View, build_view, render


class GH:
    def list_open_items(self, repo):
        return [Item(repo, 1, "issue", "I", "", frozenset({"needs:human"})), Item(repo, 2, "pr", "P", "Closes #1", frozenset(), "agent/1-x")]

    def pr_details(self, repo, n):
        return {"head_sha": "s", "head_ref": "agent/1-x", "mergeable_state": "clean", "files": ("a",), "ci": "success"}

    def last_comment_by(self, repo, n, login):
        return "pregunta"

    def list_open_issue_titles(self, repo, label):
        return {"[ops] canvas": 5}


class BrokenCoolify:
    def apps(self):
        raise RuntimeError("coolify caído")


def test_collector_isolates_source_errors(tmp_path):
    c = Collector(GH(), BrokenCoolify(), repos=("qr",), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                  state_path=tmp_path / "no-existe.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={})
    snap = c.collect(now=1000.0)
    assert [p.number for p in snap.prs] == [2] and snap.human_notes == {"qr#1": "pregunta"}
    assert snap.ops == [(5, "[ops] canvas", "https://github.com/maxiar-org/ai-dev-team/issues/5")]
    assert "coolify" in snap.errors and snap.apps == [] and snap.active == {}


def test_page_fills_age_at_request_time():
    page = Page()
    page.update("<p>hace __EDAD__ s</p>", generated_at=100.0)
    assert page.body(now=142.4) == "<p>hace 42 s</p>"


class CountingGH(GH):
    def __init__(self):
        self.details = []

    def list_open_items(self, repo):
        if repo == "roto":
            raise RuntimeError("403")
        return [Item(repo, 2, "pr", "P", "", frozenset(), "agent/1-x"), Item(repo, 3, "pr", "Q", "", frozenset({"agent:review"}), "agent/5-y")]

    def pr_details(self, repo, n):
        self.details.append((repo, n))
        return super().pr_details(repo, n)


def test_collector_details_only_for_waiting_prs_and_isolates_repos(tmp_path):
    gh = CountingGH()
    c = Collector(gh, None, repos=("roto", "qr"), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                  state_path=tmp_path / "s.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={})
    snap = c.collect(now=1000.0)
    assert gh.details == [("qr", 2)] and [p.number for p in snap.prs] == [2, 3]
    assert snap.prs[1].head_ref == "agent/5-y" and "roto" in snap.errors["github"]


def test_refresh_shows_error_page_instead_of_freezing():
    from dispatcher.estado import refresh

    class Boom:
        def collect(self, now):
            raise ValueError("roto")

    page = Page()
    page.update("<p>vieja</p>", generated_at=0.0)
    refresh(page, Boom(), now=50.0)
    assert "vieja" not in page.html and "ValueError" in page.html and page.generated_at == 50.0


ORIGIN = "https://estado.maxiar.dev"


class FakeResumen:
    def __init__(self, status="idle", fail=False):
        self.st = {"status": status, "since": "2026-10-08T00:00:00Z", "started_at": None, "last": None, "error": None}
        self.fail, self.sent = fail, []

    def status(self):
        if self.fail:
            raise RuntimeError("operador caído")
        return self.st

    def request(self, data):
        self.sent.append(data)
        self.st = dict(self.st, status="running", started_at=1000.0)
        return True


class PeriodCollector:
    def period(self, since):
        return [{"number": 23}], [], [], []


def page_with_view():
    p = Page()
    p.update("<p>x</p>", generated_at=1000.0, view=View(updated=1000.0))
    return p


def test_post_rejects_foreign_origin():
    r = FakeResumen()
    assert handle_post(page_with_view(), PeriodCollector(), r, "https://malo.dev", ORIGIN, 1000.0) == (403, "")
    assert handle_post(page_with_view(), PeriodCollector(), r, None, ORIGIN, 1000.0) == (403, "")
    assert r.sent == []


def test_post_sends_period_data_and_shows_running():
    r, page = FakeResumen(), page_with_view()
    assert handle_post(page, PeriodCollector(), r, ORIGIN, ORIGIN, 1000.0) == (303, "/")
    assert r.sent[0]["desde"] == "2026-10-08T00:00:00Z" and r.sent[0]["mergeados"] == [{"number": 23}]
    assert "generando" in page.body(now=1000.0)


def test_post_when_already_running_does_not_resend():
    r = FakeResumen(status="running")
    assert handle_post(page_with_view(), PeriodCollector(), r, ORIGIN, ORIGIN, 1000.0) == (303, "/") and r.sent == []


def test_post_when_operator_down_redirects_with_error():
    code, loc = handle_post(page_with_view(), PeriodCollector(), FakeResumen(fail=True), ORIGIN, ORIGIN, 1000.0)
    assert code == 303 and loc.startswith("/?error=") and "operador" in loc


def test_notice_is_escaped_and_shown_once():
    page = Page()
    page.update(render(build_view(Snapshot(now=1000.0))), generated_at=1000.0, view=View(updated=1000.0))
    html = page.body(now=1001.0, notice="<b>caído</b>")
    assert "&lt;b&gt;caído&lt;/b&gt;" in html and "__AVISO__" not in page.body(now=1001.0)


def test_refresh_summary_updates_page():
    page, r = page_with_view(), FakeResumen(status="running")
    refresh_summary(page, r, 1000.0)
    assert "generando" in page.body(now=1000.0)
