from datetime import date

from dispatcher.charts import day_label, fmt_hours, hbars, scale_top, stacked_bars, strip_html

SLOTS = [("claude-senior", "claude"), ("codex-senior", "codex"), ("gemini", "gemini")]


def test_scale_and_formats():
    assert [scale_top(x) for x in (0, 1.2, 2, 3.1, 7.9)] == [2, 2, 2, 4, 8]
    assert (fmt_hours(0), fmt_hours(3.14), fmt_hours(2)) == ("0 h", "3,1 h", "2 h")
    assert day_label(date(2026, 10, 12), True) == "lun 12" and day_label(date(2026, 10, 12), False) == "lun 12 oct"


def test_stacked_bars_heights_order_and_top_rounding():
    daily = [{"date": date(2026, 10, 11), "minutes": {"claude-senior": 60.0, "codex-senior": 120.0, "gemini": 0.0}},
             {"date": date(2026, 10, 12), "minutes": {"claude-senior": 0.0, "codex-senior": 0.0, "gemini": 0.0}}]
    html = stacked_bars(daily, SLOTS)
    assert html.count('class="seg') == 2                       # gemini en 0 no dibuja segmento
    assert 'height:48px;background:var(--c-claude)' in html    # 1 h de 4 h en 200 px, menos 2 de separación
    assert 'class="seg top" style="height:98px;background:var(--c-codex)' in html
    assert "dom 11 · claude-senior 1 h · codex-senior 2 h · gemini 0 h" in html
    assert ">4 h<" in html and ">0<" in html


def test_stacked_bars_30_days_labels_every_5():
    daily = [{"date": date(2026, 9, 13 + i) if i < 18 else date(2026, 10, i - 17), "minutes": {}} for i in range(30)]
    html = stacked_bars(daily, SLOTS)
    assert html.count('<span class="xl">') == 30 and html.count('<span class="xl"></span>') == 24


def test_hbars_and_strip():
    html = hbars([{"label": "codex-senior", "value": "9,5 h · 4 cortes", "fraction": 1.0, "engine": "codex", "title": "t"}])
    assert "width:100%" in html and "var(--c-codex)" in html and "9,5 h · 4 cortes" in html
    s = strip_html([{"state": "trabajando", "title": "06:00 · trabajando"}, {"state": "sin_cupo", "title": "<x>"},
                    {"state": "libre", "title": "a"}], "gemini", "gemini: 1 h")
    assert 'style="background:var(--c-gemini)"' in s and 'class="out"' in s and "&lt;x&gt;" in s and 'aria-label="gemini: 1 h"' in s
