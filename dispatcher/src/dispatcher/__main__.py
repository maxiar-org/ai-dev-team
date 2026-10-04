"""CLI: python -m dispatcher run | once | report"""

from __future__ import annotations

import argparse
import logging

from .canvas import CanvasClient
from .config import Config
from .github import GitHubClient
from .metrics import MetricsLog, summarize
from .projects import ProjectBoard
from .runner import Dispatcher, run_forever
from .state import StateStore
from .workspace import Workspace


def build(cfg: Config) -> Dispatcher:
    return Dispatcher(
        cfg,
        GitHubClient(cfg.github_token, cfg.github_org),
        CanvasClient(cfg.canvas_url, cfg.canvas_api_key),
        Workspace.for_github(cfg.projects_dir, cfg.github_org, cfg.github_token, cfg.bot_login),
        StateStore(cfg.state_path),
        MetricsLog(cfg.metrics_path),
        board=ProjectBoard(cfg.github_token, cfg.github_org, cfg.project_number) if cfg.project_number else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dispatcher")
    parser.add_argument("command", choices=["run", "once", "report"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()

    if args.command == "report":
        rows = MetricsLog(cfg.metrics_path).read()
        github = GitHubClient(cfg.github_token, cfg.github_org)
        merged: dict[tuple[str, int], bool] = {}
        for row in rows:
            key = (row["repo"], int(row["numero"]))
            if row["tipo"] == "pr" and key not in merged:
                merged[key] = github.is_merged(*key)
        print(summarize(rows, merged))
        return 0

    dispatcher = build(cfg)
    if args.command == "once":
        dispatcher.run_once()
    else:
        run_forever(dispatcher, cfg.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
