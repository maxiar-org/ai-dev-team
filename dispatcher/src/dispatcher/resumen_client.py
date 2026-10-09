"""Cliente del servidor de resúmenes del operador (red interna `resumen`, con token)."""

from __future__ import annotations

import httpx


class ResumenClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=base_url, timeout=10, headers={"Authorization": f"Bearer {token}"})

    def status(self) -> dict:
        resp = self.http.get("/resumen")
        resp.raise_for_status()
        return resp.json()

    def request(self, data: dict) -> bool:
        resp = self.http.post("/resumen", json=data)
        if resp.status_code == 409:
            return False
        resp.raise_for_status()
        return True
