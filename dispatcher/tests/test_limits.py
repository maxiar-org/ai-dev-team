from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dispatcher.limits import DEFAULT_LIMIT_S, LIMIT_MARGIN_S, detect_limit

TZ = "America/Argentina/Buenos_Aires"


def ts(text, tz=TZ):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz)).timestamp()


NOW = ts("2026-10-11 19:30")


def test_codex_time_only_later_today():
    msg = "ACP error: [-32603] Internal error: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 10:38 PM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-11 22:38") + LIMIT_MARGIN_S


def test_codex_time_only_already_passed_means_tomorrow():
    msg = "You've hit your usage limit. ... try again at 6:00 AM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-12 06:00") + LIMIT_MARGIN_S


def test_codex_full_date_with_ordinal():
    msg = "You've hit your usage limit. ... or try again at Oct 12th, 2026 12:39 AM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-12 00:39") + LIMIT_MARGIN_S


def test_claude_session_limit_in_utc():
    msg = 'ACP error: [-32603] Internal error: You\'ve hit your session limit · resets 10pm (UTC): {"errorKind": "rate_limit"}'
    now = ts("2026-10-11 21:51", "UTC")
    assert detect_limit(msg, now, TZ) == ts("2026-10-11 22:00", "UTC") + LIMIT_MARGIN_S


def test_gemini_resource_exhausted_without_time_uses_default():
    msg = "RESOURCE_EXHAUSTED You exceeded your current quota, please check your plan and billing details."
    assert detect_limit(msg, NOW, TZ) == NOW + DEFAULT_LIMIT_S


def test_limit_with_unparseable_time_uses_default():
    msg = "You've hit your usage limit. Try again at sometime soon."
    assert detect_limit(msg, NOW, TZ) == NOW + DEFAULT_LIMIT_S


@pytest.mark.parametrize("msg", ["", "flutter test falló: 3 tests", "upstream connect error 503", None])
def test_other_errors_are_not_limits(msg):
    assert detect_limit(msg, NOW, TZ) is None
