"""Configuración del dispatcher, leída de variables de entorno."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .models import Slot

ENGINES = ("claude", "codex", "gemini")

# agent_settings que espera POST /api/conversations de Canvas para cada motor ACP.
ENGINE_AGENT_SETTINGS: dict[str, dict[str, str]] = {
    "claude": {"agent_kind": "acp", "acp_server": "claude-code"},
    "codex": {"agent_kind": "acp", "acp_server": "codex"},
    # Valor a confirmar en la prueba de Gemini CLI de la fase 5a (tarea 1 del plan).
    "gemini": {"agent_kind": "acp", "acp_server": "gemini-cli"},
}
DEFAULT_SLOTS = (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))


# MCP servers que reciben siempre los agentes. Viven acá y no solo en los ajustes de Canvas porque
# esos ajustes se pueden perder (pasó el 2026-10-09). Lo configurado en Canvas se suma y pisa por nombre.
BASE_MCP_CONFIG: dict[str, dict[str, object]] = {
    "playwright": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@playwright/mcp", "--browser", "chromium",
                 "--executable-path", "/usr/bin/chromium", "--headless", "--no-sandbox"],
        "enabled": True,
    },
    # Servidor oficial de Dart y Flutter (viene con el SDK): análisis, tests, pub, árbol de widgets
    # y errores en tiempo de ejecución de la app.
    "dart": {
        "transport": "stdio",
        "command": "dart",
        "args": ["mcp-server"],
        "enabled": True,
    },
    # Imágenes con Gemini (mcp-image, ver canvas/mcp-image-gemini). Sin GEMINI_API_KEY en .env no arranca.
    # Tiene costo por imagen: el image_gen integrado de Codex sigue siendo la primera opción.
    "image": {
        "transport": "stdio",
        "command": "mcp-image-gemini",
        "args": [],
        "enabled": True,
    },
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
    project_number: int | None = None
    docs_only_repos: tuple[str, ...] = ()
    heartbeat_path: Path | None = None
    slots: tuple[Slot, ...] = DEFAULT_SLOTS
    slot_costs: dict[str, float] = field(default_factory=dict)
    limit_tz: str = "America/Argentina/Buenos_Aires"
    gemini_image_usd: float = 0.04
    limits_path: Path | None = None

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

        def parse_slots() -> tuple[Slot, ...]:
            raw = env.get("SLOTS", "").strip()
            if not raw:
                return DEFAULT_SLOTS
            slots: list[Slot] = []
            for part in (p.strip() for p in raw.split(",") if p.strip()):
                bits = part.split(":")
                if len(bits) != 3 or bits[1] not in ENGINES or not bits[0]:
                    raise ConfigError(f"SLOTS: cada puesto es nombre:motor:nivel con motor en {ENGINES}, no {part!r}")
                slots.append(Slot(*bits))
            if len({s.name for s in slots}) != len(slots):
                raise ConfigError("SLOTS tiene nombres de puesto repetidos")
            return tuple(slots)

        slots = parse_slots()
        costs: dict[str, float] = {}
        for s in slots:
            raw_cost = env.get(f"SLOT_COST_{s.name.upper().replace('-', '_')}", "").strip()
            if raw_cost:
                costs[s.name] = float(raw_cost)

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
            project_number=integer("PROJECT_NUMBER", 0) or None,
            heartbeat_path=Path(hb) if (hb := env.get("HEARTBEAT_PATH", "/state/heartbeat").strip()) else None,
            docs_only_repos=tuple(r.strip() for r in env.get("DOCS_ONLY_REPOS", "").split(",") if r.strip()),
            slots=slots,
            slot_costs=costs,
            limit_tz=env.get("LIMIT_TZ", "").strip() or "America/Argentina/Buenos_Aires",
            gemini_image_usd=float(env.get("GEMINI_IMAGE_USD", "").strip() or 0.04),
            limits_path=Path(env.get("LIMITS_PATH", "").strip() or "/pilot/limits.csv"),
        )
