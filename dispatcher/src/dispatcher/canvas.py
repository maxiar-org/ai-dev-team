"""Cliente mínimo de la API REST de OpenHands Agent Canvas (1.24)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

import httpx

from .config import BASE_MCP_CONFIG, ENGINE_AGENT_SETTINGS
from .models import ConvInfo


class CanvasBusy(RuntimeError):
    """Canvas llegó a su máximo de conversaciones en ejecución (HTTP 429)."""


def _norm(conversation_id: Any) -> str:
    return uuid.UUID(str(conversation_id)).hex


def parse_conversation(raw: dict[str, Any]) -> ConvInfo:
    prompt = completion = cache = 0
    cost = 0.0
    metrics = ((raw.get("stats") or {}).get("usage_to_metrics") or {}).values()
    for m in metrics:
        cost += float(m.get("accumulated_cost") or 0)
        usage = m.get("accumulated_token_usage") or {}
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        cache += int(usage.get("cache_read_tokens") or 0)
    return ConvInfo(
        id=_norm(raw["id"]),
        status=str(raw.get("execution_status", "")),
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_read_tokens=cache,
        cost_usd=cost,
    )


class CanvasClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            base_url=base_url, timeout=30, headers={"X-Session-API-Key": api_key}
        )

    def _mcp_config(self) -> dict[str, Any]:
        """BASE_MCP_CONFIG más los MCP servers configurados en Canvas (Customize → MCP Servers), que
        pisan por nombre. Las conversaciones creadas por API no los heredan si se manda agent_settings,
        así que se copian explícitamente."""
        configured: dict[str, Any] = {}
        try:
            resp = self.http.get("/api/settings")
            resp.raise_for_status()
            configured = (resp.json().get("agent_settings") or {}).get("mcp_config") or {}
        except (httpx.HTTPError, ValueError):
            pass
        return {**BASE_MCP_CONFIG, **configured}

    def create_conversation(self, engine: str, working_dir: str, message: str) -> str:
        agent_settings: dict[str, Any] = dict(ENGINE_AGENT_SETTINGS[engine])
        agent_settings["mcp_config"] = self._mcp_config()
        payload = {
            "agent_settings": agent_settings,
            "workspace": {"working_dir": working_dir},
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": message}],
                "run": True,
            },
        }
        resp = self.http.post("/api/conversations", json=payload)
        if resp.status_code == 429:
            raise CanvasBusy("Canvas está al máximo de conversaciones en ejecución")
        resp.raise_for_status()
        return _norm(resp.json()["id"])

    def get_conversations(self, ids: Iterable[str]) -> dict[str, ConvInfo]:
        ids = list(ids)
        if not ids:
            return {}
        resp = self.http.get("/api/conversations", params=[("ids", i) for i in ids])
        resp.raise_for_status()
        infos = (parse_conversation(raw) for raw in resp.json() if raw is not None)
        return {info.id: info for info in infos}

    def final_response(self, conversation_id: str) -> str:
        resp = self.http.get(f"/api/conversations/{conversation_id}/agent_final_response")
        resp.raise_for_status()
        return resp.json().get("response") or ""

    def pause(self, conversation_id: str) -> None:
        resp = self.http.post(f"/api/conversations/{conversation_id}/pause")
        resp.raise_for_status()
