"""Detecta límites de uso de las cuentas de los agentes y calcula hasta cuándo duran. Funciones puras."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LIMIT_MARGIN_S = 300
DEFAULT_LIMIT_S = 3600

_IS_LIMIT = re.compile(
    r"hit your (?:usage|session) limit|rate_limit|RESOURCE_EXHAUSTED|exceeded your current quota",
    re.IGNORECASE,
)
_CODEX_AT = re.compile(r"try again at\s+(?P<when>[^\n]+?)\.?\s*$", re.IGNORECASE | re.MULTILINE)
_CLAUDE_RESETS = re.compile(r"resets\s+(?P<when>\d{1,2}(?::\d{2})?\s*[ap]m)\s*\((?P<tz>[A-Za-z_/]+)\)", re.IGNORECASE)
_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b")


def _parse_clock(text: str) -> tuple[int, int] | None:
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            t = datetime.strptime(text.strip().upper(), fmt)
            return t.hour, t.minute
        except ValueError:
            continue
    return None


def _next_occurrence(hour: int, minute: int, now: float, tz: ZoneInfo) -> float:
    local_now = datetime.fromtimestamp(now, tz)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def _parse_when(when: str, now: float, tz: ZoneInfo) -> float | None:
    clean = _ORDINAL.sub(r"\1", when.strip())
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(clean, fmt).replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    clock = _parse_clock(clean)
    if clock is not None:
        return _next_occurrence(*clock, now, tz)
    return None


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo("UTC" if name.upper() == "UTC" else name)
    except Exception:
        return ZoneInfo("UTC")


def detect_limit(text: str | None, now: float, tz: str) -> float | None:
    """Hasta cuándo queda agotado el puesto (con margen), o None si el texto no es un límite de uso."""
    if not text or not _IS_LIMIT.search(text):
        return None
    until: float | None = None
    if m := _CLAUDE_RESETS.search(text):
        until = _parse_when(m.group("when"), now, _zone(m.group("tz")))
    elif m := _CODEX_AT.search(text):
        until = _parse_when(m.group("when"), now, _zone(tz))
    if until is None:
        return now + DEFAULT_LIMIT_S
    return until + LIMIT_MARGIN_S
