from pathlib import Path

from dispatcher.estado import Collector, Page, handle_post, refresh_summary
from dispatcher.models import Item
from dispatcher.render import render
from dispatcher.view import Snapshot, View, build_view


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
    assert "vieja" not in page.body(50.0) and "ValueError" in page.body(50.0) and page.generated_at == 50.0


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
    assert handle_post(page, PeriodCollector(), r, ORIGIN, ORIGIN, 1000.0) == (303, "/#resumen")
    assert r.sent[0]["desde"] == "2026-10-08T00:00:00Z" and r.sent[0]["mergeados"] == [{"number": 23}]
    assert "generando" in page.body(now=1000.0)


def test_post_when_already_running_does_not_resend():
    r = FakeResumen(status="running")
    assert handle_post(page_with_view(), PeriodCollector(), r, ORIGIN, ORIGIN, 1000.0) == (303, "/#resumen") and r.sent == []


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


# --- Arreglos de la revisión final (4e) ---

def test_origin_must_match_exactly():
    r = FakeResumen()
    for bad in ("https://estado.maxiar.dev.evil.com", "https://estado.maxiar.dev@evil.com", "http://estado.maxiar.dev"):
        assert handle_post(page_with_view(), PeriodCollector(), r, bad, ORIGIN, 1000.0) == (403, "")
    assert handle_post(page_with_view(), PeriodCollector(), r, ORIGIN + "/?x=1", ORIGIN, 1000.0)[0] == 303  # Referer
    assert len(r.sent) == 1


def test_refresh_error_clears_view_so_summary_refresh_cannot_hide_it():
    from dispatcher.estado import refresh

    class Boom:
        def collect(self, now):
            raise ValueError("roto")

    page = page_with_view()
    refresh(page, Boom(), now=50.0)
    refresh_summary(page, FakeResumen(status="running"), 60.0)
    assert page.view is None and "ValueError" in page.body(now=61.0)


def test_serve_binds_to_given_host():
    from dispatcher.estado import serve

    srv = serve(Page(), 0, host="127.0.0.1")
    assert srv.server_address[0] == "127.0.0.1"
    srv.server_close()


def test_period_searches_always_include_is_issue_or_is_pr(tmp_path):
    class RecordingGH(GH):
        def __init__(self):
            self.queries = []

        def search_since(self, query):
            self.queries.append(query)
            return []

    gh = RecordingGH()
    c = Collector(gh, None, repos=("qr",), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                  state_path=tmp_path / "s.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={})
    c.period("2026-10-08T00:00:00Z")
    assert len(gh.queries) == 3
    assert all(" is:issue " in f" {q} " or " is:pr " in f" {q} " for q in gh.queries)  # GitHub responde 422 si falta


import json

from dispatcher.estado import refresh
from dispatcher.metrics import LimitLog
from dispatcher.models import Slot


class SearchGH(GH):
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def search_since(self, query):
        self.calls += 1
        if self.fail:
            raise RuntimeError("search caído")
        if "is:pr" in query:
            return [{"repo": "qr", "number": 9, "created_at": "2026-10-12T01:00:00Z", "merged_at": "2026-10-12T03:00:00Z", "closes": 1}]
        return [{"repo": "qr", "number": 1, "closed_at": "2026-10-12T03:00:00Z", "labels": []}]

    def repo_projects(self, repos):
        return {"qr": [{"title": "QR Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/2"}]}


def collector(tmp_path, gh, **kw):
    return Collector(gh, None, repos=("qr",), org="maxiar-org", bot_login="bot", ops_repo="ai-dev-team",
                     state_path=tmp_path / "state.json", metrics_path=tmp_path / "m.csv", checker=lambda: [], expiries={},
                     limits_path=tmp_path / "limits.csv", **kw)


def test_collector_reads_exhaustion_limits_and_slots(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"active": {}, "slot_exhausted_until": {"gemini": 1234.5}}))
    LimitLog(tmp_path / "limits.csv").append("gemini", "gemini", 900.0, 1234.5, "qr#1", "429")
    slots = (Slot("gemini", "gemini", "senior"),)
    snap = collector(tmp_path, SearchGH(), slots=slots, slot_costs={"gemini": 20.0}, slot_labels={"gemini": "Gemini Pro"},
                     tz="UTC", health_links={"canvas": "https://canvas.x"}).collect(now=1000.0)
    assert snap.repo_projects == {"qr": [{"title": "QR Roadmap", "url": "https://github.com/orgs/maxiar-org/projects/2"}]}
    assert snap.health_links == {"canvas": "https://canvas.x"}
    assert snap.exhausted == {"gemini": 1234.5} and len(snap.limits) == 1 and snap.repos == ("qr",)
    assert (snap.slots, snap.slot_costs, snap.slot_labels, snap.tz) == (slots, {"gemini": 20.0}, {"gemini": "Gemini Pro"}, "UTC")
    assert [m["number"] for m in snap.merged] == [9] and [c["number"] for c in snap.closed] == [1]


def test_period_searches_are_cached(tmp_path):
    gh = SearchGH()
    c = collector(tmp_path, gh)
    c.collect(now=1000.0)
    c.collect(now=1500.0)
    assert gh.calls == 2
    c.collect(now=1700.0)
    assert gh.calls == 4


def test_period_cache_survives_search_error(tmp_path):
    gh = SearchGH()
    c = collector(tmp_path, gh)
    c.collect(now=1000.0)
    gh.fail = True
    snap = c.collect(now=2000.0)
    assert "consumo" in snap.errors and [m["number"] for m in snap.merged] == [9]


def test_parse_health_links():
    from dispatcher.estado import parse_health_links
    assert parse_health_links(" Canvas=https://canvas.x , coolify=https://c.x,mal=http://y,sinigual") == {
        "canvas": "https://canvas.x", "coolify": "https://c.x"}
    assert parse_health_links("") == {}


def test_post_redirects_to_summary_anchor():
    r, page = FakeResumen(), page_with_view()
    assert handle_post(page, PeriodCollector(), r, ORIGIN, ORIGIN, 1000.0) == (303, "/#resumen")
    code, loc = handle_post(page_with_view(), PeriodCollector(), FakeResumen(fail=True), ORIGIN, ORIGIN, 1000.0)
    assert loc.startswith("/?error=") and loc.endswith("#resumen")


def test_unknown_rango_falls_back_to_7():
    page = Page()
    page.update({"7": "siete", "30": "treinta"}, 1000.0)
    assert page.body(1000.0, rango="30") == "treinta" and page.body(1000.0, rango="x") == "siete"
    page.update("solo", 1000.0)
    assert page.body(1000.0, rango="30") == "solo"


def test_api_returns_view_json(tmp_path):
    page = Page()
    assert page.api()[0] == 503
    refresh(page, collector(tmp_path, SearchGH(), tz="UTC"), 1000.0)
    code, body = page.api()
    data = json.loads(body)
    assert code == 200 and set(data["budget"]) == {"7", "30"} and "slots" in data
