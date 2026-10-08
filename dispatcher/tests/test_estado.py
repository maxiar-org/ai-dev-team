from pathlib import Path

from dispatcher.estado import Collector, Page
from dispatcher.models import Item


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
