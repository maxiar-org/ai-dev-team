"""Vista de estado del AI Dev Team: build_view(Snapshot) -> View y render(View) -> HTML, ambas puras."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppInfo:
    name: str
    repo: str
    url: str
    status: str
    last_deploy: str | None = None
    last_deploy_status: str | None = None
    preview_template: str | None = None
    preview_prs: tuple[int, ...] = ()
