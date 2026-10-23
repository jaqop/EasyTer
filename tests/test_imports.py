"""Import smoke checks: every library module loads and exposes real behaviour."""

import datetime
import importlib

import pytest


def _check_easyter(m):
    assert m.DEFAULT_SHELL == "powershell.exe"
    assert m.PS_REDRAW_KEY == "\x1b[15~"
    assert callable(m.kitty_encode_key)
    assert callable(m.resolve_layout_key)
    assert callable(m.terminal_key_sequence)
    assert m.ENTER_DEFAULTS["shift"] == "esc_cr"
    assert callable(m._quote_shell_path)


def _check_i18n(m):
    assert m.current_language() == "en"
    assert m.t("search.no_results") == "No results"
    assert m.t("does.not.exist") == "does.not.exist"


def _check_easyterpro(m):
    assert m.__version__ == "0.1.0"


def _check_main(m):
    assert callable(m.main)


def _check_gen_schemes(m):
    assert m._MAP["purple"] == "magenta"
    assert m._MAP["brightPurple"] == "brightmagenta"
    assert m._MAP["yellow"] == "yellow"


def _check_backend(m):
    from PySide6.QtCore import QObject
    assert issubclass(m.PtyBackend, QObject)


def _check_config(m):
    assert m.DEFAULTS["theme"] == "EasyTer Dark"
    assert m.DEFAULTS["bidi"] is True
    assert m.DEFAULTS["plugins"]["disabled"] == ["sample_overlay"]
    assert m.DEFAULTS["font"]["family"] == "Consolas"


def _check_gallery(m):
    assert m.SWATCHES[0] == "red"
    assert "brightmagenta" in m.SWATCHES


def _check_palette(m):
    from PySide6.QtWidgets import QDialog
    assert issubclass(m.CommandPalette, QDialog)


def _check_panes(m):
    from PySide6.QtWidgets import QWidget
    assert issubclass(m.SplitContainer, QWidget)


def _check_pluginhost(m):
    reg = m.Registry()
    assert reg.palette_actions == []
    assert reg.loaded == []
    assert reg.failed == []


def _check_plugins_pkg(m):
    assert m.__path__


def _check_clock(m):
    assert m.format_time(datetime.datetime(2020, 1, 1, 13, 5, 9)) == "13:05:09"


def _check_activity(m):
    before = m.OUTPUT_CHUNKS
    m._on_output("chunk")
    assert m.OUTPUT_CHUNKS == before + 1


def _check_overlay(m):
    assert callable(m._paint_badge)
    assert callable(m.register)


def _check_sample_theme(m):
    spec = m._THEME
    assert spec["bg"] == "#12141c"
    assert spec["fg"] == "#c8d0e0"
    assert isinstance(spec["ansi"], dict)
    assert spec["ansi"]["red"] == "#ff6188"


def _check_timestamp(m):
    assert callable(m._insert_timestamp)
    assert callable(m.register)


def _check_tab_title(m):
    assert m.extract_title("\x1b]0;Windows\x07") == "Windows"
    assert m.extract_title("nope") is None


def _check_posh(m):
    assert m.FEATURED[0] == "kali"
    assert "paradox" in m.FAMOUS
    assert m._INIT_RE.search('oh-my-posh init pwsh --config "C:/t.omp.json"').group(2) == "C:/t.omp.json"


def _check_profiles(m):
    merged = m.merge_user_profiles(
        [m.Profile("Command Prompt", "cmd.exe")],
        [{"name": "Dev", "command": "powershell.exe -NoProfile"}],
    )
    assert [p.name for p in merged] == ["Command Prompt", "Dev"]
    assert merged[1].command == "powershell.exe -NoProfile"
    assert merged[1].source == "user"
    # a profile missing a command is skipped, not fatal
    assert m.merge_user_profiles([], [{"name": "broken"}]) == []


def _check_prompt_picker(m):
    html = m._ansi_to_html("\x1b[38;2;255;0;0mred\x1b[0m")
    assert "color:rgb(255,0,0)" in html
    assert "red" in html
    assert m._strip_noise("\x1b]0;title\x07plain") == "plain"


def _check_render(m):
    assert m.THEMES["EasyTer Dark"]["bg"] == "#0d1117"
    assert m.THEMES["EasyTer Dark"]["fg"] == "#e6edf3"
    assert "One Dark" in m.theme_names()


def _check_terminal(m):
    assert m._quote_shell_path(r"C:\Program Files\a.txt") == r'"C:\Program Files\a.txt"'
    assert m._quote_shell_path(r"C:\plain.txt") == r"C:\plain.txt"


def _check_window(m):
    from PySide6.QtWidgets import QMainWindow
    assert issubclass(m.MainWindow, QMainWindow)


_CHECKS = {
    "EasyTer": _check_easyter,
    "i18n": _check_i18n,
    "easyterpro": _check_easyterpro,
    "easyterpro.__main__": _check_main,
    "easyterpro._gen_schemes": _check_gen_schemes,
    "easyterpro.backend": _check_backend,
    "easyterpro.config": _check_config,
    "easyterpro.gallery": _check_gallery,
    "easyterpro.palette": _check_palette,
    "easyterpro.panes": _check_panes,
    "easyterpro.pluginhost": _check_pluginhost,
    "easyterpro.plugins": _check_plugins_pkg,
    "easyterpro.plugins.clock_corner": _check_clock,
    "easyterpro.plugins.sample_activity": _check_activity,
    "easyterpro.plugins.sample_overlay": _check_overlay,
    "easyterpro.plugins.sample_theme": _check_sample_theme,
    "easyterpro.plugins.sample_timestamp": _check_timestamp,
    "easyterpro.plugins.tab_title_cwd": _check_tab_title,
    "easyterpro.posh": _check_posh,
    "easyterpro.profiles": _check_profiles,
    "easyterpro.prompt_picker": _check_prompt_picker,
    "easyterpro.render": _check_render,
    "easyterpro.terminal": _check_terminal,
    "easyterpro.window": _check_window,
}


@pytest.mark.parametrize("name", sorted(_CHECKS))
def test_module_imports(name):
    mod = importlib.import_module(name)
    _CHECKS[name](mod)


def test_i18n_language_fallback_and_format():
    import i18n
    i18n.set_language("ar")
    try:
        assert i18n.current_language() == "ar"
        assert i18n.t("search.no_results") == "لا نتائج"
        assert i18n.t("claude.failed", code=3) == "انتهى claude بالرمز 3 دون ناتج."
        # unknown language falls back to English, then a missing key is the key
        i18n.set_language("zz")
        assert i18n.current_language() == "en"
        assert i18n.t("search.no_results") == "No results"
        assert i18n.t("claude.failed", code=3) == "claude exited with code 3 and no output."
        assert i18n.t("missing.key") == "missing.key"
    finally:
        i18n.set_language("en")
