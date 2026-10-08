import json

import httpx
import pytest
import respx

from dispatcher.github import GitHubClient

API = "https://api.github.com/repos/maxiar-org/qr"
HOST = "api.github.com"


def route(method, path):
    return respx.route(method=method, host=HOST, path=f"/repos/maxiar-org/qr{path}")


@pytest.fixture
def gh():
    return GitHubClient("tok", "maxiar-org")


@respx.mock
def test_list_open_items_marks_prs_and_reads_labels(gh):
    route("GET", "/pulls").respond(json=[{"number": 5, "head": {"ref": "agent/3-wa"}}])
    issues = route("GET", "/issues").respond(
        json=[
            {"number": 3, "title": "WA", "body": None, "labels": [{"name": "agent:dev"}]},
            {"number": 5, "title": "PR", "body": "Closes #3", "labels": [], "pull_request": {}},
        ]
    )
    items = gh.list_open_items("qr")
    assert [(i.number, i.kind, i.head_ref, i.body) for i in items] == [
        (3, "issue", None, ""),
        (5, "pr", "agent/3-wa", "Closes #3"),
    ]
    assert items[0].labels == frozenset({"agent:dev"})
    assert issues.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert issues.calls.last.request.url.params["state"] == "open"


@respx.mock
def test_comments_follow_pagination_and_parse_issue_number(gh):
    comments_route = route("GET", "/issues/comments")
    comments_route.side_effect = [
        httpx.Response(
            200,
            json=[{"id": 1, "issue_url": f"{API}/issues/3", "user": {"login": "maxiar"}, "body": "@openhands a"}],
            headers={"Link": f'<{API}/issues/comments?page=2>; rel="next"'},
        ),
        httpx.Response(200, json=[{"id": 2, "issue_url": f"{API}/issues/5", "user": None, "body": None}]),
    ]
    comments = gh.list_comments_since("qr", "2026-10-03T00:00:00+00:00")
    assert [(c.id, c.number, c.author, c.body) for c in comments] == [
        (1, 3, "maxiar", "@openhands a"),
        (2, 5, "", ""),
    ]
    assert comments_route.calls[0].request.url.params["since"] == "2026-10-03T00:00:00+00:00"


@respx.mock
def test_remove_label_ignores_missing_label(gh):
    removed = route("DELETE", "/issues/3/labels/agent:dev").respond(404)
    gh.remove_label("qr", 3, "agent:dev")
    assert removed.called


@respx.mock
def test_write_operations_send_expected_payloads(gh):
    labels = route("POST", "/issues/3/labels").respond(200, json=[])
    comment = route("POST", "/issues/3/comments").respond(201, json={})
    review = route("POST", "/pulls/7/requested_reviewers").respond(201, json={})
    gh.add_labels("qr", 3, ["agent:working"])
    gh.comment("qr", 3, "hola")
    gh.request_review("qr", 7, ["maxiar"])
    assert json.loads(labels.calls.last.request.content) == {"labels": ["agent:working"]}
    assert json.loads(comment.calls.last.request.content) == {"body": "hola"}
    assert json.loads(review.calls.last.request.content) == {"reviewers": ["maxiar"]}


@respx.mock
def test_get_labels_and_is_merged(gh):
    route("GET", "/issues/3").respond(json={"labels": [{"name": "needs:human"}]})
    route("GET", "/pulls/7").respond(json={"merged": True})
    assert gh.get_labels("qr", 3) == frozenset({"needs:human"})
    assert gh.is_merged("qr", 7) is True


@respx.mock
def test_server_errors_raise(gh):
    route("POST", "/issues/3/comments").respond(500)
    with pytest.raises(httpx.HTTPStatusError):
        gh.comment("qr", 3, "hola")


@respx.mock
def test_list_open_items_keeps_node_id(gh):
    route("GET", "/pulls").respond(json=[])
    route("GET", "/issues").respond(json=[{"number": 3, "node_id": "I_kw3", "title": "WA", "body": "", "labels": []}])
    assert gh.list_open_items("qr")[0].node_id == "I_kw3"


@respx.mock
def test_pr_reviews_since_become_comments_with_negative_ids(gh):
    route("GET", "/pulls/11/reviews").respond(json=[
        {"id": 5, "user": {"login": "maxiar"}, "body": "viejo", "submitted_at": "2026-10-04T01:00:00Z"},
        {"id": 6, "user": {"login": "maxiar"}, "body": "@openhands resolvé los conflictos", "submitted_at": "2026-10-04T20:54:52Z"},
        {"id": 7, "user": {"login": "maxiar"}, "body": "", "submitted_at": "2026-10-04T21:00:00Z"},
        {"id": 8, "user": None, "body": "x", "submitted_at": None},
    ])
    comments = gh.list_pr_reviews_since("qr", [11], "2026-10-04T03:31:03+00:00")
    assert [(c.id, c.number, c.author, c.body) for c in comments] == [(-6, 11, "maxiar", "@openhands resolvé los conflictos")]


@respx.mock
def test_get_merge_state(gh):
    route("GET", "/pulls/11").respond(json={"mergeable_state": "dirty"})
    route("GET", "/pulls/12").respond(json={"mergeable_state": None})
    assert gh.get_merge_state("qr", 11) == "dirty"
    assert gh.get_merge_state("qr", 12) is None


@respx.mock
def test_ops_issue_helpers(gh):
    respx.route(method="GET", host=HOST, path="/repos/maxiar-org/qr/issues").respond(
        json=[{"number": 4, "title": "[ops] canvas"}, {"number": 5, "title": "PR", "pull_request": {}}]
    )
    created = route("POST", "/issues").respond(201, json={"number": 6})
    commented = route("POST", "/issues/4/comments").respond(201, json={})
    closed = route("PATCH", "/issues/4").respond(200, json={})
    assert gh.list_open_issue_titles("qr", "ops") == {"[ops] canvas": 4}
    gh.create_issue("qr", "[ops] x", "cuerpo", ["ops"])
    gh.close_issue("qr", 4, "recuperado")
    assert json.loads(created.calls.last.request.content) == {"title": "[ops] x", "body": "cuerpo", "labels": ["ops"]}
    assert json.loads(commented.calls.last.request.content) == {"body": "recuperado"}
    assert json.loads(closed.calls.last.request.content) == {"state": "closed"}


@respx.mock
def test_pr_details_and_last_comment(gh):
    route("GET", "/pulls/7").respond(json={"head": {"sha": "abc", "ref": "agent/3-x"}, "mergeable_state": "clean"})
    route("GET", "/pulls/7/files").respond(json=[{"filename": "lib/a.dart"}, {"filename": "README.md"}])
    route("GET", "/actions/runs").respond(json={"workflow_runs": [{"status": "completed", "conclusion": "success"}]})
    route("GET", "/issues/9/comments").respond(json=[
        {"user": {"login": "maxiar-ai-dev-team-bot"}, "body": "primero"},
        {"user": {"login": "maxiar"}, "body": "humano"},
        {"user": {"login": "maxiar-ai-dev-team-bot"}, "body": "último del bot"},
    ])
    d = gh.pr_details("qr", 7)
    assert d == {"head_sha": "abc", "head_ref": "agent/3-x", "mergeable_state": "clean", "files": ("lib/a.dart", "README.md"), "ci": "success"}
    assert gh.last_comment_by("qr", 9, "maxiar-ai-dev-team-bot") == "último del bot"
