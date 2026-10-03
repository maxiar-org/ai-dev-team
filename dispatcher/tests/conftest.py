from pathlib import Path

import pytest

from dispatcher.config import Config

ROLES_DIR = Path(__file__).resolve().parents[2] / "roles"


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        github_token="ghp_test",
        github_org="maxiar-org",
        repos=("qr-generator",),
        canvas_url="http://canvas:8000",
        canvas_api_key="k",
        allowed_users=("maxiar",),
        projects_dir=tmp_path / "projects",
        state_path=tmp_path / "state.json",
        metrics_path=tmp_path / "metrics.csv",
        roles_dir=ROLES_DIR,
        bot_login="maxiar-ai-dev-team-bot",
    )
