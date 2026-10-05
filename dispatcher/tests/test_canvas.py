import json

import pytest
import respx

from dispatcher.canvas import CanvasBusy, CanvasClient
from dispatcher.models import ConvInfo

ID1 = "6f1c2d3e000040008000000000000001"
ID2 = "6f1c2d3e000040008000000000000002"
ID1_DASHED = "6f1c2d3e-0000-4000-8000-000000000001"


def route(method, path):
    return respx.route(method=method, host="canvas", path=path)


@pytest.fixture
def canvas():
    return CanvasClient("http://canvas:8000", "secret")


@respx.mock
def test_create_conversation_sends_engine_workspace_and_message(canvas):
    route("GET", "/api/settings").respond(json={"agent_settings": {"agent_kind": "llm"}})
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1_DASHED.upper()})
    assert canvas.create_conversation("claude", "/projects/qr/issue-3", "Hola") == ID1
    request = created.calls.last.request
    assert json.loads(request.content) == {
        "agent_settings": {"agent_kind": "acp", "acp_server": "claude-code"},
        "workspace": {"working_dir": "/projects/qr/issue-3"},
        "initial_message": {"role": "user", "content": [{"type": "text", "text": "Hola"}], "run": True},
    }
    assert request.headers["X-Session-API-Key"] == "secret"


@respx.mock
def test_create_conversation_raises_busy_on_429(canvas):
    route("GET", "/api/settings").respond(json={})
    route("POST", "/api/conversations").respond(429)
    with pytest.raises(CanvasBusy):
        canvas.create_conversation("codex", "/p", "Hola")


@respx.mock
def test_get_conversations_parses_status_and_sums_usage(canvas):
    listed = route("GET", "/api/conversations").respond(
        json=[
            {
                "id": ID1_DASHED,
                "execution_status": "finished",
                "stats": {
                    "usage_to_metrics": {
                        "agent": {
                            "accumulated_cost": 0.5,
                            "accumulated_token_usage": {
                                "prompt_tokens": 1000,
                                "completion_tokens": 200,
                                "cache_read_tokens": 300,
                            },
                        },
                        "condenser": {"accumulated_cost": 0.25, "accumulated_token_usage": None},
                    }
                },
            },
            None,
        ]
    )
    convs = canvas.get_conversations([ID1, ID2])
    assert convs == {ID1: ConvInfo(ID1, "finished", 1000, 200, 300, 0.75)}
    assert listed.calls.last.request.url.params.get_list("ids") == [ID1, ID2]


def test_get_conversations_with_no_ids_does_not_call_api(canvas):
    assert canvas.get_conversations([]) == {}


@respx.mock
def test_final_response_and_pause(canvas):
    route("GET", f"/api/conversations/{ID1}/agent_final_response").respond(json={"response": "VEREDICTO: APROBADO"})
    paused = route("POST", f"/api/conversations/{ID1}/pause").respond(json={"success": True})
    assert canvas.final_response(ID1) == "VEREDICTO: APROBADO"
    canvas.pause(ID1)
    assert paused.called


@respx.mock
def test_create_conversation_includes_mcp_servers_configured_in_canvas(canvas):
    mcp = {"playwright": {"transport": "stdio", "command": "npx", "args": ["-y", "@playwright/mcp"], "enabled": True}}
    route("GET", "/api/settings").respond(json={"agent_settings": {"mcp_config": mcp, "acp_server": "codex"}})
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("claude", "/p", "Hola")
    settings = json.loads(created.calls.last.request.content)["agent_settings"]
    assert settings == {"agent_kind": "acp", "acp_server": "claude-code", "mcp_config": mcp}


@respx.mock
def test_create_conversation_works_if_settings_are_unreadable(canvas):
    route("GET", "/api/settings").respond(500)
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("codex", "/p", "Hola")
    assert "mcp_config" not in json.loads(created.calls.last.request.content)["agent_settings"]
