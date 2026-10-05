"""Configuración del dispatcher, leída de variables de entorno."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENGINES = ("claude", "codex")

# agent_settings que espera POST /api/conversations de Canvas para cada motor ACP.
ENGINE_AGENT_SETTINGS: dict[str, dict[str, str]] = {
    "claude": {"agent_kind": "acp", "acp_server": "claude-code"},
    "codex": {"agent_kind": "acp", "acp_server": "codex"},
}


class ConfigError(ValueError):
    """La configuración del entorno es inválida o incompleta."""


@dataclass(frozen=True)
class Config:
    github_token: str
    github_org: str
    repos: tuple[str, ...]
    canvas_url: str
    canvas_api_key: str
    allowed_users: tuple[str, ...]
    projects_dir: Path
    state_path: Path
    metrics_path: Path
    roles_dir: Path
    bot_login: str
    poll_seconds: int = 60
    task_timeout_min: int = 60
    max_review_rounds: int = 2
    idle_grace_seconds: int = 120
    default_dev_engine: str = "codex"
    project_number: int | None = None
    qa_engine: str = "codex"
    docs_engine: str = "claude"
    docs_only_repos: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env

        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"Falta la variable de entorno {name}")
            return value

        def csv(name: str) -> tuple[str, ...]:
            values = tuple(v.strip() for v in required(name).split(",") if v.strip())
            if not values:
                raise ConfigError(f"{name} no tiene valores")
            return values

        def integer(name: str, default: int) -> int:
            raw = env.get(name, "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} debe ser un entero, no {raw!r}") from exc
            if value <= 0:
                raise ConfigError(f"{name} debe ser mayor que 0")
            return value

        def engine_var(name: str, default: str) -> str:
            value = env.get(name, "").strip() or default
            if value not in ENGINES:
                raise ConfigError(f"{name} debe ser uno de {ENGINES}, no {value!r}")
            return value

        engine = engine_var("DEFAULT_DEV_ENGINE", "codex")

        return cls(
            github_token=required("GITHUB_TOKEN"),
            github_org=required("GITHUB_ORG"),
            repos=csv("REPOS"),
            canvas_url=required("CANVAS_URL").rstrip("/"),
            canvas_api_key=required("CANVAS_API_KEY"),
            allowed_users=tuple(u.lower() for u in csv("ALLOWED_USERS")),
            projects_dir=Path(env.get("PROJECTS_DIR", "/projects")),
            state_path=Path(env.get("STATE_PATH", "/state/state.json")),
            metrics_path=Path(env.get("METRICS_PATH", "/pilot/metrics.csv")),
            roles_dir=Path(env.get("ROLES_DIR", "/app/roles")),
            bot_login=env.get("BOT_LOGIN", "").strip() or "maxiar-ai-dev-team-bot",
            poll_seconds=integer("POLL_SECONDS", 60),
            task_timeout_min=integer("TASK_TIMEOUT_MIN", 60),
            max_review_rounds=integer("MAX_REVIEW_ROUNDS", 2),
            idle_grace_seconds=integer("IDLE_GRACE_SECONDS", 120),
            default_dev_engine=engine,
            project_number=integer("PROJECT_NUMBER", 0) or None,
            qa_engine=engine_var("QA_ENGINE", "codex"),
            docs_engine=engine_var("DOCS_ENGINE", "claude"),
            docs_only_repos=tuple(r.strip() for r in env.get("DOCS_ONLY_REPOS", "").split(",") if r.strip()),
        )
