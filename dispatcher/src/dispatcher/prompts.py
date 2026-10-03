"""Arma el prompt de cada rol a partir de las plantillas de roles/."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .models import Item, Role

ROLE_FILES: dict[str, str] = {"dev": "dev.md", "review": "reviewer.md", "fix": "fix.md"}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def slugify(text: str, max_len: int = 40) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].strip("-") or "tarea"


def dev_branch(number: int, title: str) -> str:
    return f"agent/{number}-{slugify(title)}"


def build_prompt(roles_dir: Path, role: Role, item: Item, org: str, instruction: str = "") -> str:
    template = (roles_dir / ROLE_FILES[role]).read_text(encoding="utf-8")
    branch = item.head_ref if item.kind == "pr" and item.head_ref else dev_branch(item.number, item.title)
    values = {
        "org": org,
        "repo": item.repo,
        "number": str(item.number),
        "kind": "issue" if item.kind == "issue" else "pull request",
        "title": item.title,
        "body": item.body.strip() or "(sin descripción)",
        "branch": branch,
        "instruction": instruction.strip() or "(sin instrucciones adicionales)",
    }
    # Una sola pasada: el texto que viene de GitHub nunca se vuelve a expandir.
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], template)
