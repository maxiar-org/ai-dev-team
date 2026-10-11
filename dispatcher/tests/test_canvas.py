import json

import pytest
import respx

from dispatcher.canvas import CanvasBusy, CanvasClient
from dispatcher.config import BASE_MCP_CONFIG
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
        "agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "mcp_config": BASE_MCP_CONFIG},
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
def test_create_conversation_always_includes_base_mcp_servers(canvas):
    route("GET", "/api/settings").respond(json={"agent_settings": {"mcp_config": {}}})
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("claude", "/p", "Hola")
    settings = json.loads(created.calls.last.request.content)["agent_settings"]
    assert settings == {"agent_kind": "acp", "acp_server": "claude-code", "mcp_config": BASE_MCP_CONFIG}
    assert set(BASE_MCP_CONFIG) == {"playwright", "dart"}


@respx.mock
def test_create_conversation_adds_mcp_servers_configured_in_canvas(canvas):
    extra = {"otro": {"transport": "stdio", "command": "otro-mcp", "args": [], "enabled": True}}
    route("GET", "/api/settings").respond(json={"agent_settings": {"mcp_config": extra, "acp_server": "codex"}})
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("claude", "/p", "Hola")
    mcp = json.loads(created.calls.last.request.content)["agent_settings"]["mcp_config"]
    assert mcp == {**BASE_MCP_CONFIG, **extra}


@respx.mock
def test_canvas_settings_override_a_base_mcp_server(canvas):
    pw = {"transport": "stdio", "command": "npx", "args": ["-y", "@playwright/mcp", "--headless"], "enabled": True}
    route("GET", "/api/settings").respond(json={"agent_settings": {"mcp_config": {"playwright": pw}}})
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("codex", "/p", "Hola")
    mcp = json.loads(created.calls.last.request.content)["agent_settings"]["mcp_config"]
    assert mcp["playwright"] == pw and mcp["dart"] == BASE_MCP_CONFIG["dart"]


@respx.mock
def test_create_conversation_uses_base_mcp_if_settings_are_unreadable(canvas):
    route("GET", "/api/settings").respond(500)
    created = route("POST", "/api/conversations").respond(201, json={"id": ID1})
    canvas.create_conversation("codex", "/p", "Hola")
    assert json.loads(created.calls.last.request.content)["agent_settings"]["mcp_config"] == BASE_MCP_CONFIG
