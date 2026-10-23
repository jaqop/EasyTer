"""Pure-logic tests for EasyTer: key encoding, OSC/SGR escapes, path quoting, config."""

import base64
import json

import pyte
import pytest

import EasyTer
from easyterpro import terminal as pro_terminal

# ---------------------------------------------------------------- kitty keys ----

def test_kitty_escape_is_csi_u_and_plain_arrows_stay_legacy():
    qt = EasyTer.Qt
    assert EasyTer.kitty_encode_key(qt.Key_Escape, False, False, False) == "\x1b[27u"
    assert EasyTer.kitty_encode_key(qt.Key_Escape, True, False, False) == "\x1b[27;5u"
    assert EasyTer.kitty_encode_key(qt.Key_Escape, False, False, True) == "\x1b[27;2u"
    # unmodified arrows are left to the legacy encoder
    assert EasyTer.kitty_encode_key(qt.Key_Up, False, False, False) is None
    assert EasyTer.kitty_encode_key(qt.Key_Left, False, False, False) is None


def test_kitty_modified_arrows_use_xterm_modifier_form():
    qt = EasyTer.Qt
    # modifier = 1 + shift + 2*alt + 4*ctrl
    assert EasyTer.kitty_encode_key(qt.Key_Up, False, False, True) == "\x1b[1;2A"
    assert EasyTer.kitty_encode_key(qt.Key_Down, True, False, False) == "\x1b[1;5B"
    assert EasyTer.kitty_encode_key(qt.Key_Right, False, True, False) == "\x1b[1;3C"
    assert EasyTer.kitty_encode_key(qt.Key_Left, True, True, False) == "\x1b[1;7D"
    assert EasyTer.kitty_encode_key(qt.Key_Home, True, False, True) == "\x1b[1;6H"
    assert EasyTer.kitty_encode_key(qt.Key_End, False, True, True) == "\x1b[1;4F"


def test_kitty_ctrl_letter_uses_lowercase_codepoint():
    qt = EasyTer.Qt
    # ctrl+a is CSI 97;5u (ASCII 'a'), not the keycode of 'A'
    assert EasyTer.kitty_encode_key(qt.Key_A, True, False, False) == "\x1b[97;5u"
    assert EasyTer.kitty_encode_key(qt.Key_Z, False, True, False) == "\x1b[122;3u"
    # shift alone on a letter is still text, so the legacy path handles it
    assert EasyTer.kitty_encode_key(qt.Key_A, False, False, True) is None
    # ctrl+shift+a keeps the lowercase codepoint and stacks both modifiers (1+1+4)
    assert EasyTer.kitty_encode_key(qt.Key_A, True, False, True) == "\x1b[97;6u"


def test_kitty_ctrl_space_enter_tab_backspace():
    qt = EasyTer.Qt
    assert EasyTer.kitty_encode_key(qt.Key_Return, False, False, False) is None
    assert EasyTer.kitty_encode_key(qt.Key_Return, True, False, False) == "\x1b[13;5u"
    assert EasyTer.kitty_encode_key(qt.Key_Enter, False, True, False) == "\x1b[13;3u"
    assert EasyTer.kitty_encode_key(qt.Key_Tab, False, False, True) == "\x1b[9;2u"
    assert EasyTer.kitty_encode_key(qt.Key_Backtab, False, False, True) == "\x1b[9;2u"
    assert EasyTer.kitty_encode_key(qt.Key_Backspace, False, True, False) == "\x1b[127;3u"
    # ctrl+space must not collapse to NUL
    assert EasyTer.kitty_encode_key(qt.Key_Space, True, False, False) == "\x1b[32;5u"
    assert EasyTer.kitty_encode_key(qt.Key_Space, False, False, False) is None


def test_kitty_punctuation_and_unhandled_function_key():
    qt = EasyTer.Qt
    assert EasyTer.kitty_encode_key(qt.Key_1, True, False, False) == "\x1b[49;5u"
    assert EasyTer.kitty_encode_key(qt.Key_F1, True, False, False) is None


# ----------------------------------------------------------- escape sequences ----

def test_scan_bidi_modes_last_sequence_wins():
    data = "pre\x1b[8lmid\x1b[2 k"
    explicit, base, pos = EasyTer.scan_bidi_modes(data, False, None)
    assert explicit is True
    assert base is True
    # last_pos is the latest BDSM or SCP match; the SCP here is after the BDSM
    assert pos == data.rfind("\x1b[2 k")
    assert pos > data.rfind("\x1b[8l")
    data = "\x1b[8l...\x1b[8h\x1b[1 k"
    explicit, base, pos = EasyTer.scan_bidi_modes(data, True, True)
    assert explicit is False
    assert base is False
    assert pos == data.rfind("\x1b[1 k")


def test_scan_bidi_ignores_private_modes_and_reports_no_match():
    explicit, base, pos = EasyTer.scan_bidi_modes("\x1b[?8h\x1b[?1049l\x1b[?2004h", False, None)
    assert (explicit, base, pos) == (False, None, -1)
    assert EasyTer.scan_bidi_modes("plain", True, False) == (True, False, -1)


def test_osc133_marks_and_kitty_keyboard_query():
    end = EasyTer.OSC133_RE.search("\x1b]133;D;0\x07")
    assert end.group(1) == "D"
    assert end.group(2) == ";0"
    start = EasyTer.OSC133_RE.search("ready\x1b]133;B\x1b\\next")
    assert start.group(1) == "B"
    assert start.group(2) == ""
    noisy = "hi\x1b[>1u there\x1b[?0u"
    assert EasyTer.KITTY_KB_RE.sub("", noisy) == "hi there"


def test_osc_edit_and_cwd_reports():
    edit = EasyTer.OSC_EDIT_RE.search("\x1b]6969;C:\\src\\main.py\x07")
    assert edit.group(1) == "C:\\src\\main.py"
    cwd = EasyTer.OSC99_RE.search('\x1b]9;9;"C:\\Users\\me"\x07')
    assert cwd.group(1) == "C:\\Users\\me"
    bare = EasyTer.OSC99_RE.search("\x1b]9;9;D:\\work\x1b\\")
    assert bare.group(1) == "D:\\work"


def test_osc52_payload_is_the_base64_body():
    payload = base64.b64encode("مرحبا".encode()).decode("ascii")
    match = EasyTer.OSC52_RE.search("\x1b]52;c;" + payload + "\x07")
    assert base64.b64decode(match.group(1)).decode("utf-8") == "مرحبا"
    # a query (no payload) does not match the write form
    assert EasyTer.OSC52_RE.search("\x1b]52;c;?\x07") is None


def test_color_codes_named_and_truecolor():
    assert EasyTer._color_codes("red", 30) == "31"
    assert EasyTer._color_codes("red", 40) == "41"
    assert EasyTer._color_codes("brightred", 30) == "91"
    assert EasyTer._color_codes("brightred", 40) == "101"
    assert EasyTer._color_codes("ff00aa", 30) == "38;2;255;0;170"
    assert EasyTer._color_codes("ff00aa", 40) == "48;2;255;0;170"
    assert EasyTer._color_codes("default", 30) is None
    assert EasyTer._color_codes("", 30) is None
    assert EasyTer._color_codes(None, 30) is None
    assert EasyTer._color_codes("zzzzzz", 30) is None
    assert EasyTer._color_codes("not-a-color", 30) is None


def test_ansi_to_runs_truecolor_reset_and_background():
    text = "\x1b[38;2;255;0;0mred\x1b[0m plain\x1b[48;2;0;0;255m blue"
    assert EasyTer.ansi_to_runs(text) == [
        ("red", "#ff0000", None),
        (" plain", None, None),
        (" blue", None, "#0000ff"),
    ]


def test_line_to_ansi_round_trips_sgr_red():
    screen = pyte.Screen(8, 1)
    pyte.Stream(screen).feed("\x1b[31mHi\x1b[0m")
    encoded = EasyTer.line_to_ansi(screen.buffer[0], 2)
    assert encoded == "\x1b[0;31mHi\x1b[0m"


def test_osc7_file_url_becomes_a_windows_path():
    data = "\x1b]7;file://localhost/C:/Users/me/My%20Documents\x07"
    match = EasyTer.OSC7_RE.search(data)
    assert EasyTer.PtyBackend._osc7_to_path(match.group(1)) == "C:\\Users\\me\\My Documents"
    st = "\x1b]7;file://wsl.local/c/Users/me\x1b\\"
    match = EasyTer.OSC7_RE.search(st)
    assert EasyTer.PtyBackend._osc7_to_path(match.group(1)) == "c:\\Users\\me"


def test_osc7_unix_and_bare_windows_paths_are_not_rewritten():
    convert = EasyTer.PtyBackend._osc7_to_path
    assert convert("/home/user") == "/home/user"
    assert convert("C:\\Users\\me") == "C:\\Users\\me"
    assert convert("/C:") == "C:\\"


# ------------------------------------------------------------------ quoting ----

@pytest.mark.parametrize("quote", [EasyTer._quote_shell_path, pro_terminal._quote_shell_path])
def test_quote_shell_path_wraps_whitespace_only(quote):
    assert quote(r"C:\plain.txt") == r"C:\plain.txt"
    assert quote(r"C:\My Documents\a.txt") == r'"C:\My Documents\a.txt"'
    assert quote("a\tb") == '"a\tb"'
    assert quote('C:\\My "Files"\\a.txt') == '"C:\\My \\"Files\\"\\a.txt"'
    # a quote with no whitespace is not wrapped
    assert quote('C:\\weird"name.txt') == 'C:\\weird"name.txt'
    assert quote("") == ""
    # shell metacharacters without whitespace stay bare (whitespace rule only)
    assert quote(r"C:\a&b.txt") == r"C:\a&b.txt"


def test_quoted_drop_chunks_join_with_a_space():
    parts = [r"C:\plain.txt", r"C:\My Documents\a.txt"]
    joined = " ".join(EasyTer._quote_shell_path(p) for p in parts)
    assert joined == 'C:\\plain.txt "C:\\My Documents\\a.txt"'


# -------------------------------------------------------------------- config ----

@pytest.fixture
def settings_snapshot():
    saved = dict(EasyTer.SETTINGS)
    yield
    EasyTer.SETTINGS.clear()
    EasyTer.SETTINGS.update(saved)


def test_load_settings_overlays_saved_keys(tmp_path, monkeypatch, settings_snapshot):
    cfg = tmp_path / "easyter_config.json"
    cfg.write_text(json.dumps({
        "font_size": 21,
        "language": "ar",
        "opacity": 0.4,
        "cursor_style": "bar",
    }), encoding="utf-8")
    monkeypatch.setattr(EasyTer, "CONFIG_PATH", str(cfg))
    EasyTer.load_settings()
    assert EasyTer.SETTINGS["font_size"] == 21
    assert EasyTer.SETTINGS["language"] == "ar"
    assert EasyTer.SETTINGS["opacity"] == 0.4
    assert EasyTer.SETTINGS["cursor_style"] == "bar"
    # keys absent from the file keep their built-in defaults
    assert EasyTer.SETTINGS["font_family"] == "JetBrains Mono"
    assert EasyTer.SETTINGS["shell_integration"] is True
    assert EasyTer.SETTINGS["enter_shift"] == "esc_cr"
    assert EasyTer.SETTINGS["enter_ctrl"] == "lf"
    assert EasyTer.SETTINGS["enter_alt"] == "esc_cr"


def test_load_settings_ignores_missing_and_invalid_files(tmp_path, monkeypatch, settings_snapshot):
    monkeypatch.setattr(EasyTer, "CONFIG_PATH", str(tmp_path / "missing.json"))
    EasyTer.load_settings()
    assert EasyTer.SETTINGS["font_size"] == 13

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(EasyTer, "CONFIG_PATH", str(bad))
    EasyTer.load_settings()
    assert EasyTer.SETTINGS["font_size"] == 13

    listed = tmp_path / "list.json"
    listed.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(EasyTer, "CONFIG_PATH", str(listed))
    EasyTer.load_settings()
    assert EasyTer.SETTINGS["font_size"] == 13
    assert EasyTer.SETTINGS["language"] == "en"


def test_load_themes_reads_name_or_filename_and_skips_bad_files(tmp_path, monkeypatch):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "ocean.json").write_text(json.dumps({
        "name": "Ocean",
        "bg": "#001122",
        "fg": "#abcdef",
        "ansi": {"red": "#ff0000"},
    }), encoding="utf-8")
    (themes / "dusk.json").write_text(json.dumps({
        "bg": "#010101",
        "fg": "#fefefe",
    }), encoding="utf-8")
    (themes / "broken.json").write_text("{", encoding="utf-8")
    (themes / "incomplete.json").write_text(json.dumps({"name": "Nope", "bg": "#000"}), encoding="utf-8")
    monkeypatch.setattr(EasyTer, "THEMES_DIR", str(themes))
    for name in ("Ocean", "dusk", "Nope", "broken", "incomplete"):
        EasyTer.THEMES.pop(name, None)
    try:
        EasyTer.load_themes()
        assert EasyTer.THEMES["Ocean"] == ("#001122", "#abcdef", {"red": "#ff0000"})
        assert EasyTer.THEMES["dusk"] == ("#010101", "#fefefe", None)
        assert "Nope" not in EasyTer.THEMES
        assert "broken" not in EasyTer.THEMES
        assert "incomplete" not in EasyTer.THEMES
    finally:
        for name in ("Ocean", "dusk"):
            EasyTer.THEMES.pop(name, None)


def test_easyterpro_deep_merge_nests_dicts_and_replaces_lists():
    from easyterpro.config import _deep_merge
    base = {
        "font": {"family": "Consolas", "size": 13},
        "bidi": True,
        "profiles": [{"name": "a", "command": "cmd.exe"}],
    }
    merged = _deep_merge(base, {
        "font": {"size": 18},
        "bidi": False,
        "profiles": [],
    })
    assert merged == {
        "font": {"family": "Consolas", "size": 18},
        "bidi": False,
        "profiles": [],
    }
    # the base object is not mutated
    assert base["font"]["size"] == 13
    assert base["profiles"] == [{"name": "a", "command": "cmd.exe"}]
    assert _deep_merge({"font": {"size": 13}}, {"font": "Consolas"})["font"] == "Consolas"
    assert _deep_merge({"a": 1}, None) == {"a": 1}


def test_easyterpro_config_load_merges_user_file(tmp_path, monkeypatch, qapp):
    from easyterpro import config as cfgmod
    monkeypatch.setattr(cfgmod, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(json.dumps({
        "theme": "Nord",
        "font": {"size": 18},
        "plugins": {"disabled": ["clock_corner"]},
    }), encoding="utf-8")
    cfg = cfgmod.Config()
    assert cfg.get("theme") == "Nord"
    assert cfg.get("font", "size") == 18
    assert cfg.get("font", "family") == "Consolas"
    assert cfg.get("bidi") is True
    assert cfg.get("plugins", "disabled") == ["clock_corner"]
    # nested default settings survive when the user file omits them
    assert cfg.get("plugins", "settings") == {}
    assert cfg.get("nope", "missing", default="fallback") == "fallback"


def test_easyterpro_config_invalid_json_keeps_defaults(tmp_path, monkeypatch, qapp):
    from easyterpro import config as cfgmod
    monkeypatch.setattr(cfgmod, "CONFIG_DIR", str(tmp_path))
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", str(path))
    cfg = cfgmod.Config()
    assert cfg.get("theme") == "EasyTer Dark"
    assert cfg.get("font", "size") == 13


def test_easyterpro_config_writes_defaults_then_set_persists(tmp_path, monkeypatch, qapp):
    from easyterpro import config as cfgmod
    monkeypatch.setattr(cfgmod, "CONFIG_DIR", str(tmp_path))
    path = tmp_path / "config.json"
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", str(path))
    cfg = cfgmod.Config()
    assert path.is_file()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["theme"] == "EasyTer Dark"
    assert written["plugins"]["disabled"] == ["sample_overlay"]

    seen = []
    cfg.changed.connect(lambda: seen.append(cfg.get("font", "size")))
    cfg.set(20, "font", "size")
    assert cfg.get("font", "size") == 20
    assert cfg.get("font", "family") == "Consolas"
    assert seen == [20]
    again = json.loads(path.read_text(encoding="utf-8"))
    assert again["font"]["size"] == 20
    assert again["font"]["family"] == "Consolas"
