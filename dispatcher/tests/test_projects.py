import json

import httpx

import pytest
import respx

from dispatcher.projects import ProjectBoard, ProjectError

FIELD = {
    "id": "F1",
    "options": [{"id": "o-backlog", "name": "Backlog"}, {"id": "o-review", "name": "En review"}],
}


def page(nodes, has_next=False, cursor=None):
    return {
        "data": {
            "organization": {
                "projectV2": {
                    "id": "P1",
                    "field": FIELD,
                    "items": {"pageInfo": {"hasNextPage": has_next, "endCursor": cursor}, "nodes": nodes},
                }
            }
        }
    }


def node(item_id, repo, number, status):
    return {
        "id": item_id,
        "fieldValueByName": {"name": status} if status else None,
        "content": {"number": number, "repository": {"name": repo}},
    }


@pytest.fixture
def board():
    return ProjectBoard("tok", "maxiar-org", 1)


@respx.mock
def test_load_paginates_and_maps_items_by_key(board):
    route = respx.post("https://api.github.com/graphql")
    route.side_effect = [
        httpx.Response(200, json=page([node("I1", "qr", 3, "Backlog")], True, "c1")),
        httpx.Response(200, json=page([node("I2", "qr", 9, None), {"id": "I3", "fieldValueByName": None, "content": None}])),
    ]
    assert board.load() == {"qr#3": ("I1", "Backlog"), "qr#9": ("I2", None)}
    second = json.loads(route.calls[1].request.content)
    assert second["variables"]["after"] == "c1"
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok"


@respx.mock
def test_add_and_set_column_use_project_field_and_option_ids(board):
    route = respx.post("https://api.github.com/graphql")
    route.side_effect = [
        httpx.Response(200, json=page([])),
        httpx.Response(200, json={"data": {"addProjectV2ItemById": {"item": {"id": "NEW"}}}}),
        httpx.Response(200, json={"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "NEW"}}}}),
    ]
    board.load()
    assert board.add("I_node") == "NEW"
    board.set_column("NEW", "En review")
    added = json.loads(route.calls[1].request.content)["variables"]
    updated = json.loads(route.calls[2].request.content)["variables"]
    assert added == {"p": "P1", "c": "I_node"}
    assert updated == {"p": "P1", "i": "NEW", "f": "F1", "o": "o-review"}


@respx.mock
def test_unknown_column_and_graphql_errors_raise(board):
    route = respx.post("https://api.github.com/graphql")
    route.side_effect = [
        httpx.Response(200, json=page([])),
        httpx.Response(200, json={"errors": [{"message": "Resource not accessible"}]}),
    ]
    board.load()
    with pytest.raises(ProjectError, match="Inexistente"):
        board.set_column("NEW", "Inexistente")
    with pytest.raises(ProjectError, match="Resource not accessible"):
        board.add("I_node")
