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
    assert match.group("host") == "localhost"
    assert EasyTer.PtyBackend._osc7_to_path(match.group("path")) == "C:\\Users\\me\\My Documents"
    st = "\x1b]7;file://wsl.local/c/Users/me\x1b\\"
    match = EasyTer.OSC7_RE.search(st)
    assert match.group("host") == "wsl.local"
    assert EasyTer.PtyBackend._osc7_to_path(match.group("path")) == "c:\\Users\\me"


def test_osc7_unix_and_bare_windows_paths_are_not_rewritten():
    convert = EasyTer.PtyBackend._osc7_to_path
    assert convert("/home/user") == "/home/user"
    assert convert("C:\\Users\\me") == "C:\\Users\\me"
    assert convert("/C:") == "C:\\"


# ------------------------------------------------------------------ quoting ----

@pytest.mark.parametrize("quote", [EasyTer._quote_shell_path, pro_terminal._quote_shell_path])
def test_quote_shell_path_matches_the_running_shell(quote):
    from easyterpro.shellquote import shell_family

    # PowerShell: always single-quoted, embedded quotes doubled.
    assert quote(r"C:\plain.txt") == r"'C:\plain.txt'"
    assert quote(r"C:\My Documents\a.txt", "pwsh.exe") == r"'C:\My Documents\a.txt'"
    assert quote("C:\\it's a $file.txt", "powershell.exe") == r"'C:\it''s a $file.txt'"
    assert quote(r"C:\a&b;$(whoami)`x.txt", "pwsh") == r"'C:\a&b;$(whoami)`x.txt'"
    assert quote("a\tb", "powershell") == "'a\tb'"
    assert quote("C:\\a\r\nb.txt", "powershell.exe") == r"'C:\ab.txt'"
    assert quote("\r\n", "powershell") is None
    assert quote("", "powershell") is None

    # cmd: double quotes. & | < > ^ are literal inside them. ! is caret-escaped.
    # " and % cannot be quoted safely, and a trailing ^ escapes the closer.
    assert quote(r"C:\plain.txt", "cmd.exe") == r'"C:\plain.txt"'
    assert quote(r"C:\My Documents\a.txt", "cmd") == r'"C:\My Documents\a.txt"'
    assert quote(r"C:\a&b|c<d>e^f.txt", "cmd.exe") == r'"C:\a&b|c<d>e^f.txt"'
    assert quote(r"C:\bang!.txt", "cmd.exe") == r'"C:\bang^!.txt"'
    assert quote('C:\\a"b.txt', "cmd") is None
    assert quote(r"C:\100%.txt", "cmd.exe") is None
    assert quote("C:\\ends^\n", "cmd") is None
    assert quote("C:\\a\r\nb.txt", "cmd.exe") == r'"C:\ab.txt"'

    # bash / WSL: single quotes, embedded quote as '\'' .
    assert quote("/mnt/c/it's.txt", "wsl.exe") == "'/mnt/c/it'\\''s.txt'"
    assert quote("a\rb", r"C:\Program Files\Git\usr\bin\bash.exe") == "'ab'"
    assert quote(r"C:\a&b.txt", "bash") == r"'C:\a&b.txt'"

    # An unknown shell is not guessed.
    assert quote(r"C:\a.txt", r"C:\tools\custom.exe") is None
    assert shell_family("powershell.exe -NoProfile") == "powershell"
    assert shell_family(["pwsh.exe"]) == "powershell"
    assert shell_family("cmd.exe /k") == "cmd"
    assert shell_family(r"C:\Program Files\Git\usr\bin\bash.exe") == "posix"
    assert shell_family("wsl.exe -d Ubuntu") == "posix"
    assert shell_family(r"C:\tools\custom.exe") is None


def test_local_path_gate_does_not_neutralize_shell_syntax():
    from easyterpro.localpath import accept_local_path
    from easyterpro.shellquote import quote_dropped_text

    path = r"C:\a'; & $(calc) `whoami`.txt"
    assert accept_local_path(path) == path
    dropped = quote_dropped_text([path, "C:\\ok\r\n"], "powershell.exe")
    assert dropped == "'C:\\a''; & $(calc) `whoami`.txt' 'C:\\ok'"
    assert "\r" not in dropped and "\n" not in dropped
    # one unquotable neighbor refuses the whole drop
    assert quote_dropped_text([r"C:\ok.txt", r"C:\100%.txt"], "cmd.exe") is None
    assert quote_dropped_text([r"C:\ok.txt"], "cmd.exe") == r'"C:\ok.txt"'


def test_quoted_drop_chunks_join_with_a_space():
    from easyterpro.shellquote import quote_dropped_text

    parts = [r"C:\plain.txt", r"C:\My Documents\a.txt"]
    assert quote_dropped_text(parts, "powershell.exe") == r"'C:\plain.txt' 'C:\My Documents\a.txt'"
    assert quote_dropped_text(parts, "cmd.exe") == r'"C:\plain.txt" "C:\My Documents\a.txt"'


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


# ------------------------------------------------------- paste and OSC 52 ----

def test_paste_guard_warns_for_multiline_controls_and_size():
    from easyterpro.pasteguard import PASTE_LARGE, guarded_paste, paste_needs_warning

    assert paste_needs_warning("echo hi") is False
    assert paste_needs_warning("echo\thi") is False
    assert paste_needs_warning("a\nb") is True
    assert paste_needs_warning("a\rb") is True
    assert paste_needs_warning("a\x1bb") is True
    assert paste_needs_warning("a" * PASTE_LARGE) is False
    assert paste_needs_warning("a" * (PASTE_LARGE + 1)) is True
    assert guarded_paste("a\nb", bracketed=True, protection=True, confirm=lambda _t: False) is None
    assert guarded_paste("a\nb", bracketed=False, protection=False, confirm=lambda _t: False) == "a\rb"
    assert guarded_paste("", bracketed=True, protection=True, confirm=lambda _t: True) is None
    wrapped = guarded_paste("echo hi\necho\x1b[201~calc", bracketed=True, protection=False,
                            confirm=lambda _t: False)
    assert wrapped == "\x1b[200~echo hi\recho" + "calc" + "\x1b[201~"


def test_easyter_paste_uses_the_same_guard(qapp, monkeypatch):
    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
    written = []

    class Backend:
        bracketed_paste = False

        def write(self, text):
            written.append(text)

    widget.backend = Backend()
    widget.read_only = False
    monkeypatch.setitem(EasyTer.SETTINGS, "paste_protection", True)
    qapp.clipboard().setText("only-tab\there")
    widget._confirm_paste = lambda text: (_ for _ in ()).throw(AssertionError(text))
    widget._do_paste()
    assert written == ["only-tab\there"]

    written.clear()
    qapp.clipboard().setText("a\nb")
    widget._confirm_paste = lambda _text: False
    widget._do_paste()
    assert written == []
    widget.read_only = True
    widget._confirm_paste = lambda _text: True
    widget._do_paste()
    assert written == []


def test_pro_paste_uses_the_same_guard(qapp):
    widget = pro_terminal.TerminalWidget.__new__(pro_terminal.TerminalWidget)
    written = []

    class Backend:
        bracketed_paste = True

        def write(self, text):
            written.append(text)

    widget.backend = Backend()
    widget.scroll_offset = 4
    qapp.clipboard().setText("echo hi")
    widget._confirm_paste = lambda text: (_ for _ in ()).throw(AssertionError(text))
    widget._paste_clipboard()
    assert written == ["\x1b[200~echo hi\x1b[201~"]
    assert widget.scroll_offset == 0

    written.clear()
    widget.scroll_offset = 2
    qapp.clipboard().setText("echo hi\r\necho there")
    widget._confirm_paste = lambda _text: False
    widget._paste_clipboard()
    assert written == []

    widget._confirm_paste = lambda _text: True
    qapp.clipboard().setText("echo hi\necho there\x1b[201~calc")
    widget._paste_clipboard()
    assert written == ["\x1b[200~echo hi\recho therecalc\x1b[201~"]

    written.clear()
    widget.backend.bracketed_paste = False
    qapp.clipboard().setText("ping\x1b")
    widget._confirm_paste = lambda _text: False
    widget._paste_clipboard()
    assert written == []
    widget._confirm_paste = lambda _text: True
    widget._paste_clipboard()
    assert written == ["ping\x1b"]


def test_pro_backend_tracks_bracketed_paste():
    from easyterpro.backend import PtyBackend

    backend = PtyBackend.__new__(PtyBackend)
    backend.alt_screen = False
    backend.bracketed_paste = False
    backend._scan_tail = ""
    backend.alt_screen_changed = type("Sig", (), {"emit": staticmethod(lambda *_a: None)})()
    backend._scan_alt("ready\x1b[?2004h")
    assert backend.bracketed_paste is True
    backend._scan_alt("\x1b[?2004l")
    assert backend.bracketed_paste is False


def test_osc52_write_is_off_until_enabled(monkeypatch):
    backend = EasyTer.PtyBackend.__new__(EasyTer.PtyBackend)
    emitted = []
    written = []
    backend.clipboard_set = type("Sig", (), {"emit": staticmethod(lambda text: emitted.append(text))})()
    backend.write = lambda text: written.append(text)
    payload = base64.b64encode("hello".encode()).decode("ascii")
    sequence = "\x1b]52;c;" + payload + "\x07"
    monkeypatch.setitem(EasyTer.SETTINGS, "osc52_clipboard", False)
    backend._scan_osc52(sequence)
    assert emitted == []
    assert written == []
    monkeypatch.setitem(EasyTer.SETTINGS, "osc52_clipboard", True)
    backend._scan_osc52(sequence)
    assert emitted == ["hello"]
    assert written == []


def test_osc52_confirm_size_and_one_dialog(qapp, monkeypatch):
    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
    widget._osc52_confirm_open = False
    monkeypatch.setitem(EasyTer.SETTINGS, "osc52_clipboard", False)
    qapp.clipboard().setText("original")
    widget._on_osc52("copied")
    assert qapp.clipboard().text() == "original"

    monkeypatch.setitem(EasyTer.SETTINGS, "osc52_clipboard", True)
    monkeypatch.setattr(EasyTer, "confirm_osc52", lambda *_a, **_k: False)
    widget._on_osc52("copied")
    assert qapp.clipboard().text() == "original"

    monkeypatch.setattr(EasyTer, "confirm_osc52", lambda *_a, **_k: True)
    widget._on_osc52("copied")
    assert qapp.clipboard().text() == "copied"

    widget._on_osc52("x" * (EasyTer.OSC52_MAX_BYTES + 1))
    assert qapp.clipboard().text() == "copied"

    nested = []

    def confirm(parent, text):
        nested.append(text)
        widget._on_osc52("second")
        return True

    monkeypatch.setattr(EasyTer, "confirm_osc52", confirm)
    widget._on_osc52("first")
    assert nested == ["first"]
    assert qapp.clipboard().text() == "first"

    exact = b"A" * EasyTer.OSC52_MAX_BYTES
    assert EasyTer._decode_osc52(base64.b64encode(exact).decode("ascii")) == "A" * EasyTer.OSC52_MAX_BYTES
    over = b"A" * (EasyTer.OSC52_MAX_BYTES + 1)
    assert EasyTer._decode_osc52(base64.b64encode(over).decode("ascii")) is None
    assert EasyTer._decode_osc52("?") is None


def test_osc52_query_does_not_read_or_reply(qapp, monkeypatch):
    qapp.clipboard().setText("secret")
    backend = EasyTer.PtyBackend.__new__(EasyTer.PtyBackend)
    emitted = []
    written = []
    backend.clipboard_set = type("Sig", (), {"emit": staticmethod(lambda text: emitted.append(text))})()
    backend.write = lambda text: written.append(text)
    monkeypatch.setitem(EasyTer.SETTINGS, "osc52_clipboard", True)
    backend._scan_osc52("\x1b]52;c;?\x07")
    backend._scan_osc52("\x1b]52;;?\x1b\\")
    backend._scan_osc52("\x1b]52;p;?\x07")
    assert written == []
    assert emitted == []
    assert qapp.clipboard().text() == "secret"
    assert backend._osc52_query_reply("\x1b]52;c;?\x07") is None


def test_live_prompt_command_is_gated_and_quoted():
    from easyterpro.window import live_prompt_command

    themes = r"C:\Users\me\.poshthemes"
    cmd = live_prompt_command(themes, "kali")
    assert cmd == (
        "oh-my-posh init pwsh --config "
        r"'C:\Users\me\.poshthemes\kali.omp.json' | Invoke-Expression 2>$null" + "\r"
    )
    injected = live_prompt_command(themes, "kali'; calc #")
    assert injected is not None
    assert injected.startswith("oh-my-posh init pwsh --config '")
    assert "''" in injected
    head, _, tail = injected.partition("| Invoke-Expression")
    assert head.endswith("' ")
    assert "calc" in head
    assert tail == " 2>$null\r"
    assert live_prompt_command(themes, "..\\..\\Windows\\System32\\calc") is None
    assert live_prompt_command(r"\\evil\share", "kali") is None
    assert live_prompt_command(themes, "kali\r\ncalc") is None
    assert live_prompt_command(themes, 'ka"li') is None
    assert live_prompt_command("/home/me/.poshthemes", "kali") is None
