"""Prepara una copia del repo por tarea en el volumen compartido /projects."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class WorkspaceError(RuntimeError):
    """No se pudo preparar la copia del repo. El mensaje no contiene el token."""


class Workspace:
    def __init__(self, projects_dir: Path, remote_base: str, org: str, bot_name: str, bot_email: str):
        self.projects_dir = projects_dir
        self.remote_base = remote_base
        self.org = org
        self.bot_name = bot_name
        self.bot_email = bot_email

    @classmethod
    def for_github(cls, projects_dir: Path, org: str, token: str, bot_login: str) -> Workspace:
        return cls(
            projects_dir,
            f"https://x-access-token:{token}@github.com",
            org,
            bot_login,
            f"{bot_login}@users.noreply.github.com",
        )

    def path_for(self, repo: str, kind: str, number: int) -> Path:
        return self.projects_dir / repo / f"{kind}-{number}"

    def _redact(self, text: str) -> str:
        # git a veces imprime el remoto sin esquema; y nunca debe salir un usuario:token@.
        for secret in (self.remote_base, self.remote_base.split("://", 1)[-1]):
            text = text.replace(secret, "<remoto>")
        return re.sub(r"[^/\s:@]+:[^/\s@]+@", "<credenciales>@", text)

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        try:
            done = subprocess.run(
                ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=600
            )
        except subprocess.CalledProcessError as exc:
            raise WorkspaceError(f"git {args[0]} falló: {self._redact(exc.stderr.strip())}") from None
        except subprocess.TimeoutExpired:
            raise WorkspaceError(f"git {args[0]} tardó más de 10 minutos") from None
        return done.stdout.strip()

    def prepare(self, repo: str, kind: str, number: int, branch: str | None) -> Path:
        path = self.path_for(repo, kind, number)
        url = f"{self.remote_base}/{self.org}/{repo}.git"
        if (path / ".git").exists():
            self._git("remote", "set-url", "origin", url, cwd=path)
            self._git("fetch", "origin", "--prune", cwd=path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", url, str(path))
        self._git("config", "user.name", self.bot_name, cwd=path)
        self._git("config", "user.email", self.bot_email, cwd=path)
        if branch is None:
            self._git("remote", "set-head", "origin", "--auto", cwd=path)
            branch = self._git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=path).removeprefix("origin/")
        self._git("checkout", "-f", "-B", branch, f"origin/{branch}", cwd=path)
        # -fd y no -fdx: los archivos ignorados (cachés de build) se conservan.
        self._git("clean", "-fd", cwd=path)
        return path
