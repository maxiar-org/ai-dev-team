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
