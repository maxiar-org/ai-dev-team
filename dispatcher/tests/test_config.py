import pytest

from dispatcher.config import Config, ConfigError

BASE = {
    "GITHUB_TOKEN": "t",
    "GITHUB_ORG": "maxiar-org",
    "REPOS": "qr-generator, agent-playground",
    "CANVAS_URL": "http://canvas:8000/",
    "CANVAS_API_KEY": "k",
    "ALLOWED_USERS": "Maxiar",
}


def test_from_env_parses_lists_and_defaults():
    cfg = Config.from_env(BASE)
    assert cfg.repos == ("qr-generator", "agent-playground")
    assert cfg.canvas_url == "http://canvas:8000"
    assert cfg.allowed_users == ("maxiar",)
    assert cfg.default_dev_engine == "codex"
    assert (cfg.task_timeout_min, cfg.max_review_rounds, cfg.idle_grace_seconds) == (60, 2, 120)
    assert cfg.bot_login == "maxiar-ai-dev-team-bot"


def test_missing_required_variable_names_it():
    env = dict(BASE)
    del env["GITHUB_TOKEN"]
    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        Config.from_env(env)


@pytest.mark.parametrize(
    "name,value",
    [("DEFAULT_DEV_ENGINE", "gemini"), ("POLL_SECONDS", "abc"), ("TASK_TIMEOUT_MIN", "0")],
)
def test_invalid_values_are_rejected(name, value):
    with pytest.raises(ConfigError, match=name):
        Config.from_env({**BASE, name: value})
