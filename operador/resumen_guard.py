"""Hook PreToolUse del resumen del operador: lista blanca de comandos (fase 4e).

Claude Code, en modo dontAsk, aprueba solo comandos que considera de lectura (p. ej. `docker ps`), y eso depende de
su versión. Este hook decide con nuestras reglas: solo `gh issue|pr|run` de lectura sobre maxiar-org, sin
metacaracteres de shell. Salida 0 = sigue, 2 = bloqueado (Claude ve el motivo). Cada decisión queda en un log.
Python 3.11, solo librería estándar.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / "resumenes" / "guard.log"
ORG = "maxiar-org"
SUBCOMMANDS = {("issue", "view"), ("issue", "list"), ("pr", "view"), ("pr", "list"), ("pr", "diff"), ("run", "view")}
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/#=,@-]+$")
BLOCKED_FLAGS = {"--web", "-w"}


def allowed(command: str) -> bool:
    parts = command.split()
    if len(parts) < 3 or parts[0] != "gh" or (parts[1], parts[2]) not in SUBCOMMANDS:
        return False
    for i, tok in enumerate(parts[3:], start=3):
        if not SAFE_TOKEN.match(tok) or tok in BLOCKED_FLAGS:
            return False
        if "://" in tok and not tok.startswith(f"https://github.com/{ORG}/"):
            return False
        if tok.startswith("-R") and tok != "-R":  # forma pegada (-Rotro/repo)
            return False
        if tok.startswith("--repo=") and not tok[len("--repo="):].startswith(f"{ORG}/"):
            return False
        if tok in ("--repo", "-R") and (i + 1 >= len(parts) or not parts[i + 1].startswith(f"{ORG}/")):
            return False
    return True


def _log(decision: str, detail: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with LOG_PATH.open("a") as fh:
            fh.write(f"{decision} {stamp} {detail[:300]}\n")
    except OSError:
        pass


def main(stdin=sys.stdin) -> int:
    try:
        event = json.load(stdin)
    except ValueError:
        _log("BLOQUEADO", "entrada inválida")
        return 2
    tool = event.get("tool_name", "")
    command = (event.get("tool_input") or {}).get("command", "") if tool == "Bash" else ""
    if tool == "Bash" and allowed(command):
        _log("PERMITIDO", command)
        return 0
    _log("BLOQUEADO", f"{tool}: {command or json.dumps(event.get('tool_input'))}")
    print("Solo se permite gh issue/pr/run de lectura sobre maxiar-org, sin metacaracteres de shell.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
