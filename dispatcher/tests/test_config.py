import pytest

from dispatcher.config import Config, ConfigError
from dispatcher.models import Slot

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
    assert (cfg.task_timeout_min, cfg.max_review_rounds, cfg.idle_grace_seconds) == (60, 2, 120)
    assert cfg.bot_login == "maxiar-ai-dev-team-bot"


def test_missing_required_variable_names_it():
    env = dict(BASE)
    del env["GITHUB_TOKEN"]
    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        Config.from_env(env)


@pytest.mark.parametrize(
    "name,value",
    [("POLL_SECONDS", "abc"), ("TASK_TIMEOUT_MIN", "0")],
)
def test_invalid_values_are_rejected(name, value):
    with pytest.raises(ConfigError, match=name):
        Config.from_env({**BASE, name: value})


def test_project_number_is_optional():
    assert Config.from_env(BASE).project_number is None
    assert Config.from_env({**BASE, "PROJECT_NUMBER": "1"}).project_number == 1
    with pytest.raises(ConfigError, match="PROJECT_NUMBER"):
        Config.from_env({**BASE, "PROJECT_NUMBER": "x"})


def test_docs_only_repos():
    assert Config.from_env(BASE).docs_only_repos == ()
    cfg = Config.from_env({**BASE, "DOCS_ONLY_REPOS": "ai-dev-team, x"})
    assert cfg.docs_only_repos == ("ai-dev-team", "x")


def test_default_slots_keep_one_per_current_engine():
    cfg = Config.from_env(BASE)
    assert cfg.slots == (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))
    assert (cfg.limit_tz, cfg.gemini_image_usd, cfg.slot_costs) == ("America/Argentina/Buenos_Aires", 0.04, {})


def test_slots_and_costs_from_env():
    env = {**BASE, "SLOTS": "claude-senior:claude:senior, codex-senior:codex:senior, gemini:gemini:senior",
           "SLOT_COST_CLAUDE_SENIOR": "100", "SLOT_COST_GEMINI": "20", "LIMIT_TZ": "UTC", "GEMINI_IMAGE_USD": "0.039"}
    cfg = Config.from_env(env)
    assert [s.name for s in cfg.slots] == ["claude-senior", "codex-senior", "gemini"]
    assert cfg.slot_costs == {"claude-senior": 100.0, "gemini": 20.0}
    assert (cfg.limit_tz, cfg.gemini_image_usd) == ("UTC", 0.039)


@pytest.mark.parametrize("value", ["solo-nombre", "x:openai:senior", "a:claude:senior,a:codex:senior"])
def test_invalid_slots_are_rejected(value):
    with pytest.raises(ConfigError, match="SLOTS"):
        Config.from_env({**BASE, "SLOTS": value})


def test_heartbeat_path_default_and_disable():
    assert str(Config.from_env(BASE).heartbeat_path) == "/state/heartbeat"
    assert Config.from_env({**BASE, "HEARTBEAT_PATH": ""}).heartbeat_path is None
