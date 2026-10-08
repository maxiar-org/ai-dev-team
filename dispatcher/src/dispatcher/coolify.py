"""Cliente mínimo de la API de Coolify (solo lectura) para la vista de estado."""

from __future__ import annotations

import json

import httpx

from .view import AppInfo


def _https(url: str) -> str:
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


class CoolifyClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=base_url, timeout=20,
                                         headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def apps(self) -> list[AppInfo]:
        resp = self.http.get("/applications")
        resp.raise_for_status()
        out = []
        for a in resp.json():
            url = (a.get("fqdn") or "").split(",")[0]
            if not url and a.get("docker_compose_domains"):
                raw = a["docker_compose_domains"]
                domains = json.loads(raw) if isinstance(raw, str) else raw
                url = next((d.get("domain", "") for d in domains.values() if d.get("domain")), "")
            deps = self.http.get(f"/deployments/applications/{a['uuid']}", params={"take": 30})
            deps.raise_for_status()
            body = deps.json()
            items = body.get("deployments", []) if isinstance(body, dict) else body
            main = next((d for d in items if not d.get("pull_request_id")), None)
            previews = sorted({int(d["pull_request_id"]) for d in items
                               if d.get("pull_request_id") and d.get("status") == "finished"})
            out.append(AppInfo(
                name=a.get("name", ""), repo=a.get("git_repository", ""), url=_https(url), status=a.get("status", ""),
                last_deploy=main.get("created_at") if main else None,
                last_deploy_status=main.get("status") if main else None,
                preview_template=a.get("preview_url_template"), preview_prs=tuple(previews),
            ))
        return out
