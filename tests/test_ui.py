import io
from types import SimpleNamespace

import pytest

from ipmg import __version__
from ipmg.reporting import ui


@pytest.fixture(autouse=True)
def clean_glyph_cache():
    ui.reset_glyphs()
    yield
    ui.reset_glyphs()


def fake_console(encoding="utf-8", legacy_windows=False):
    return SimpleNamespace(
        legacy_windows=legacy_windows,
        file=io.TextIOWrapper(io.BytesIO(), encoding=encoding),
    )


def test_glyphs_fall_back_to_ascii_on_a_limited_terminal():
    glyphs = ui._detect_glyphs(fake_console(encoding="ascii"))

    assert glyphs is ui._ASCII_GLYPHS
    assert glyphs["dot"] == "*"


def test_glyphs_fall_back_on_legacy_windows():
    assert ui._detect_glyphs(fake_console(legacy_windows=True)) is ui._ASCII_GLYPHS


def test_glyphs_use_unicode_on_a_utf8_terminal():
    glyphs = ui._detect_glyphs(fake_console())

    assert glyphs is ui._UNICODE_GLYPHS
    assert glyphs["dot"] == "●"


def test_glyph_lookup_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(ui, "_detect_glyphs", lambda *_a: calls.append(1) or ui._UNICODE_GLYPHS)

    ui.glyph("dot")
    ui.glyph("ok")

    assert len(calls) == 1


def test_every_glyph_has_an_ascii_counterpart():
    assert set(ui._UNICODE_GLYPHS) == set(ui._ASCII_GLYPHS)
    assert all(value.isascii() for value in ui._ASCII_GLYPHS.values())


def test_bar_is_proportional_and_clamped():
    assert ui.bar(0.5, width=10).plain == ui.glyph("bar_full") * 5 + ui.glyph("bar_empty") * 5
    assert ui.bar(0, width=4).plain == ui.glyph("bar_empty") * 4
    assert ui.bar(1, width=4).plain == ui.glyph("bar_full") * 4
    # Out-of-range input must not produce a negative-width bar.
    assert len(ui.bar(-3, width=6).plain) == 6
    assert len(ui.bar(9, width=6).plain) == 6


def test_header_shows_the_version_and_subtitle(capsys):
    ui.header("scan")
    out = capsys.readouterr().out

    assert "ipmg" in out
    assert __version__ in out
    assert "scan" in out


def test_fields_align_values(capsys):
    ui.fields([("Source", "targets.txt"), ("Targets", "3 hosts")])
    lines = capsys.readouterr().out.splitlines()

    assert lines[0].index("targets.txt") == lines[1].index("3 hosts")


def test_field_list_repeats_the_indent_only(capsys):
    ui.field_list("Saved", ["a.csv", "b.md"])
    lines = capsys.readouterr().out.splitlines()

    assert "Saved" in lines[0]
    assert "Saved" not in lines[1]
    assert lines[0].index("a.csv") == lines[1].index("b.md")


def test_status_lines_carry_a_glyph(capsys):
    ui.success("done")
    ui.warn("careful")
    ui.error("broken")
    out = capsys.readouterr().out

    assert f"{ui.glyph('ok')} done" in out
    assert f"{ui.glyph('warn')} careful" in out
    assert f"{ui.glyph('fail')} broken" in out


def test_joined_uses_the_separator(capsys):
    ui.joined(["3 hosts", "0.08s"])
    assert f"3 hosts {ui.glyph('sep')} 0.08s" in capsys.readouterr().out

    ui.joined([])
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, "-"), (0.471, "471ms"), (3.1, "3.10s"), (75, "1m 15s")],
)
def test_format_duration(seconds, expected):
    assert ui.format_duration(seconds) == expected


def test_format_latency_and_percent():
    assert ui.format_latency(None) == "-"
    assert ui.format_latency(12.345) == "12.3 ms"
    assert ui.format_percent(66.666) == "66.7%"


def test_plural():
    assert ui.plural(1, "host") == "1 host"
    assert ui.plural(0, "host") == "0 hosts"
    assert ui.plural(3, "host") == "3 hosts"


def test_table_rows_never_wrap(capsys):
    grid = ui.table("Name", "Value", min_widths=[None, 6])
    grid.add_row("a-very-long-name-that-will-not-fit-on-one-line", "123456")
    ui.print_table(grid)

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2  # header + a single row
