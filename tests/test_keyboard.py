"""Keyboard input for AI CLIs and the Arabic layout.

Kitty mode encodes Shift/Ctrl/Alt+Enter as CSI-u. Legacy mode sends the
sequence Claude Code's /terminal-setup writes for Shift+Enter (ESC CR),
with Ctrl+Enter and Alt+Enter configurable the same way.

Arabic layouts name a key by its character. Ctrl/Alt chords use the Windows
virtual key, or the US PC-101 scan code when that virtual key is unusable.
AltGr (Ctrl+Alt) still inserts a character when it differs from the US one.
"""

import json

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

import EasyTer

# Windows virtual keys and US PC-101 set-1 scan codes for the letters the
# shortcuts and the interrupt path depend on.
_VK = {ch: ord(ch) for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_SCAN = {}
for _base, _letters in ((0x10, "QWERTYUIOP"), (0x1E, "ASDFGHJKL"), (0x2C, "ZXCVBNM")):
    for _i, _ch in enumerate(_letters):
        _SCAN[_ch] = _base + _i


def _key(key, modifiers, *, text="", scan=0, vk=0):
    return QKeyEvent(
        QEvent.Type.KeyPress, key, modifiers, int(scan), int(vk), 0, text)


@pytest.fixture
def settings_snapshot():
    saved = dict(EasyTer.SETTINGS)
    yield
    EasyTer.SETTINGS.clear()
    EasyTer.SETTINGS.update(saved)


def test_kitty_modified_enter_table():
    """Shift/Ctrl/Alt+Enter under the kitty disambiguate flag.

    Claude Code and Codex treat CSI 13;2u as Shift+Enter (newline) and
    CSI 13;3u as Alt+Enter (newline). CSI 13;5u is Ctrl+Enter.
    Main Enter and keypad Enter use the same code point.
    """
    table = (
        (False, False, False, None),
        (False, False, True, "\x1b[13;2u"),
        (False, True, False, "\x1b[13;3u"),
        (True, False, False, "\x1b[13;5u"),
        (True, False, True, "\x1b[13;6u"),
        (False, True, True, "\x1b[13;4u"),
        (True, True, False, "\x1b[13;7u"),
        (True, True, True, "\x1b[13;8u"),
    )
    for key in (Qt.Key_Return, Qt.Key_Enter):
        for ctrl, alt, shift, expected in table:
            got = EasyTer.kitty_encode_key(key, ctrl, alt, shift)
            assert got == expected, (int(key), ctrl, alt, shift, got)


def test_legacy_modified_enter_table(settings_snapshot):
    """Legacy bytes. Shift+Enter is ESC CR, the /terminal-setup sequence."""
    EasyTer.SETTINGS["enter_shift"] = "esc_cr"
    EasyTer.SETTINGS["enter_ctrl"] = "lf"
    EasyTer.SETTINGS["enter_alt"] = "esc_cr"
    assert EasyTer.legacy_modified_enter(False, False, False) == "\r"
    shift = EasyTer.legacy_modified_enter(False, False, True)
    assert shift == "\x1b\r"
    assert list(shift.encode("latin1")) == [0x1B, 0x0D]
    ctrl = EasyTer.legacy_modified_enter(True, False, False)
    assert ctrl == "\n"
    assert list(ctrl.encode("latin1")) == [0x0A]
    assert EasyTer.legacy_modified_enter(False, True, False) == "\x1b\r"
    # stacked modifiers stay unambiguous (kitty modifier numbering)
    assert EasyTer.legacy_modified_enter(True, False, True) == "\x1b[13;6u"
    assert EasyTer.legacy_modified_enter(True, True, False) == "\x1b[13;7u"
    assert EasyTer.legacy_modified_enter(False, True, True) == "\x1b[13;4u"

    modes = (
        ("esc_cr", "\x1b\r"),
        ("lf", "\n"),
        ("csi_u", "\x1b[13;2u"),
        ("modify_other_keys", "\x1b[27;2;13~"),
        ("cr", "\r"),
    )
    for mode, expected in modes:
        assert EasyTer.legacy_modified_enter(False, False, True, mode=mode) == expected
    assert EasyTer.legacy_modified_enter(True, False, False, mode="csi_u") == "\x1b[13;5u"
    assert EasyTer.legacy_modified_enter(False, True, False, mode="csi_u") == "\x1b[13;3u"
    assert EasyTer.legacy_modified_enter(True, False, False, mode="modify_other_keys") == "\x1b[27;5;13~"
    assert EasyTer.legacy_modified_enter(False, True, False, mode="modify_other_keys") == "\x1b[27;3;13~"
    assert EasyTer.legacy_modified_enter(True, True, True, mode="csi_u") == "\x1b[13;8u"
    # an unknown token falls back to the chord default, not to a submit
    assert EasyTer.legacy_modified_enter(False, False, True, mode="nope") == "\x1b\r"
    assert EasyTer.legacy_modified_enter(True, False, False, mode="nope") == "\n"


def test_terminal_sequence_uses_kitty_then_legacy(settings_snapshot):
    EasyTer.SETTINGS["enter_shift"] = "esc_cr"
    EasyTer.SETTINGS["enter_ctrl"] = "lf"
    EasyTer.SETTINGS["enter_alt"] = "esc_cr"
    qt = Qt
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, False, False, True, "", kitty=True) == "\x1b[13;2u"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, True, False, False, "", kitty=True) == "\x1b[13;5u"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Enter, False, True, False, "", kitty=True) == "\x1b[13;3u"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, False, False, True, "", kitty=False) == "\x1b\r"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, True, False, False, "", kitty=False) == "\n"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, False, True, False, "", kitty=False) == "\x1b\r"
    # plain Enter is CR in both modes (kitty leaves it on the legacy path)
    assert EasyTer.terminal_key_sequence(
        qt.Key_Return, False, False, False, "", kitty=True) == "\r"
    assert EasyTer.terminal_key_sequence(
        qt.Key_Enter, False, False, False, "", kitty=False) == "\r"
    # AltGr text is never rewritten into a ctrl or kitty sequence
    assert EasyTer.terminal_key_sequence(
        qt.Key_C, True, True, False, "€", kitty=True, altgr_text="€") == "€"


def test_saved_enter_mode_overrides_default(tmp_path, monkeypatch, settings_snapshot):
    cfg = tmp_path / "easyter_config.json"
    cfg.write_text(json.dumps({
        "enter_shift": "lf",
        "enter_ctrl": "csi_u",
        "enter_alt": "modify_other_keys",
    }), encoding="utf-8")
    monkeypatch.setattr(EasyTer, "CONFIG_PATH", str(cfg))
    EasyTer.load_settings()
    assert EasyTer.legacy_modified_enter(False, False, True) == "\n"
    assert EasyTer.legacy_modified_enter(True, False, False) == "\x1b[13;5u"
    assert EasyTer.legacy_modified_enter(False, True, False) == "\x1b[27;3;13~"
    # a token that is not a mode keeps the built-in default
    EasyTer.SETTINGS["enter_shift"] = "nope"
    EasyTer.SETTINGS["enter_alt"] = ""
    assert EasyTer.legacy_modified_enter(False, False, True) == "\x1b\r"
    assert EasyTer.legacy_modified_enter(False, True, False) == "\x1b\r"


def test_arabic_ctrl_letters_use_native_virtual_key():
    """Ctrl+letter follows VK, not the Arabic character Qt put on the event."""
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        event = _key(
            Qt.Key_unknown, Qt.ControlModifier,
            text="ؤ", scan=0, vk=_VK[ch])
        key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
        assert altgr is None
        assert key == int(getattr(Qt, "Key_" + ch))
        # the pty byte is the control character, never the Arabic letter
        seq = EasyTer.terminal_key_sequence(key, True, False, False, "ؤ", kitty=False)
        assert seq == chr(ord(ch) - ord("A") + 1)
        assert seq != "ؤ"


def test_arabic_ctrl_falls_back_to_us_pc101_scan():
    """A missing or non-key virtual key uses the US PC-101 position."""
    # VK 0, scan code of the physical C key
    event = _key(Qt.Key_unknown, Qt.ControlModifier, text="ؤ", scan=_SCAN["C"], vk=0)
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert (key, altgr) == (int(Qt.Key_C), None)
    # Qt sometimes reports the Arabic code point (U+0624 ARABIC LETTER WAW
    # WITH HAMZA ABOVE, the Arabic 101 character on the C key) as the VK.
    event = _key(Qt.Key_unknown, Qt.ControlModifier, text="ؤ", scan=_SCAN["C"], vk=0x0624)
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert (key, altgr) == (int(Qt.Key_C), None)
    # the virtual key wins when both are present and they disagree
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier,
        scan=_SCAN["A"], vk=_VK["C"])
    key, _altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert key == int(Qt.Key_C)


def test_arabic_ctrl_c_interrupts_legacy_and_kitty():
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier,
        text="ؤ", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_C)
    assert EasyTer.terminal_key_sequence(
        key, True, False, False, "ؤ", kitty=False) == "\x03"
    assert EasyTer.terminal_key_sequence(
        key, True, False, False, "ؤ", kitty=True) == "\x1b[99;5u"


def test_arabic_app_shortcuts_use_physical_key():
    """Copy, paste, tabs, splits and the other letter chords use the physical key."""
    chords = {
        "C": Qt.Key_C,   # copy / interrupt
        "V": Qt.Key_V,   # paste
        "Z": Qt.Key_Z,
        "D": Qt.Key_D,
        "L": Qt.Key_L,
        "R": Qt.Key_R,
        "T": Qt.Key_T,   # new tab
        "E": Qt.Key_E,   # split
        "O": Qt.Key_O,
        "N": Qt.Key_N,
        "W": Qt.Key_W,
        "P": Qt.Key_P,
        "F": Qt.Key_F,   # search
        "S": Qt.Key_S,   # editor save
    }
    for ch, qt_key in chords.items():
        for mods in (Qt.ControlModifier, Qt.ControlModifier | Qt.ShiftModifier):
            event = _key(Qt.Key_unknown, mods, text="ش", scan=_SCAN[ch], vk=_VK[ch])
            key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
            assert altgr is None
            assert key == int(qt_key), ch
    # OEM keys used by zoom (Ctrl+= / Ctrl+-) and settings (Ctrl+,)
    oem = (
        (0xBB, 0x0D, Qt.Key_Equal),
        (0xBD, 0x0C, Qt.Key_Minus),
        (0xBC, 0x33, Qt.Key_Comma),
    )
    for vk, scan, qt_key in oem:
        event = _key(Qt.Key_unknown, Qt.ControlModifier, text="ج", scan=scan, vk=vk)
        key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
        assert altgr is None and key == int(qt_key)
    # Alt+Left still resolves when the event key is unknown
    event = _key(Qt.Key_unknown, Qt.AltModifier, scan=0, vk=0x25)
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_Left)


def test_arabic_ctrl_v_is_paste_key_not_the_arabic_letter():
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier,
        text="ر", scan=_SCAN["V"], vk=_VK["V"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert key == int(Qt.Key_V) and altgr is None
    # the paste shortcut consumes this chord; if it did not, the pty would
    # see SYN, not the Arabic letter on the V key
    assert EasyTer.terminal_key_sequence(
        key, True, False, False, "ر", kitty=False) == "\x16"
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier | Qt.ShiftModifier,
        text="ر", scan=_SCAN["V"], vk=_VK["V"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert key == int(Qt.Key_V) and altgr is None


def test_altgr_keeps_distinct_characters():
    mods = Qt.ControlModifier | Qt.AltModifier
    # Euro, the Arabic letter on C, and the two-character lam-alef on B
    for text, vk, scan in (("€", _VK["C"], _SCAN["C"]),
                           ("ؤ", _VK["C"], _SCAN["C"]),
                           ("لا", _VK["B"], _SCAN["B"])):
        event = _key(Qt.Key_unknown, mods, text=text, scan=scan, vk=vk)
        _key_code, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
        assert altgr == text
        assert EasyTer.terminal_key_sequence(
            Qt.Key_C, True, True, False, text, kitty=True, altgr_text=altgr) == text
    # GroupSwitch (AltGr on some builds) with no separate Ctrl bit
    event = _key(
        Qt.Key_unknown, Qt.GroupSwitchModifier,
        text="€", scan=_SCAN["E"], vk=_VK["E"])
    _key_code, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr == "€"
    # Shift does not turn a distinct AltGr character into a shortcut
    event = _key(
        Qt.Key_unknown, mods | Qt.ShiftModifier,
        text="ؤ", scan=_SCAN["C"], vk=_VK["C"])
    _key_code, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr == "ؤ"


def test_altgr_same_us_character_stays_a_shortcut():
    mods = Qt.ControlModifier | Qt.AltModifier
    event = _key(Qt.Key_unknown, mods, text="c", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_C)
    # case does not count as a different character
    event = _key(
        Qt.Key_unknown, mods | Qt.ShiftModifier,
        text="C", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_C)
    # empty text is not a character
    event = _key(Qt.Key_unknown, mods, text="", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_C)


def test_ctrl_without_alt_does_not_emit_arabic_text():
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier,
        text="ؤ", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert altgr is None and key == int(Qt.Key_C)
    assert EasyTer.terminal_key_sequence(
        key, True, False, False, event.text(), kitty=False) == "\x03"


def test_plain_arabic_text_is_not_remapped():
    """No Ctrl/Alt: the Arabic letter, a word, and an IME commit stay text."""
    event = _key(
        Qt.Key_unknown, Qt.NoModifier,
        text="ؤ", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert key == int(Qt.Key_unknown) and altgr is None
    assert EasyTer.terminal_key_sequence(
        key, False, False, False, "ؤ", kitty=False) == "ؤ"
    assert EasyTer.terminal_key_sequence(
        Qt.Key_unknown, False, False, False, "مرحبا", kitty=False) == "مرحبا"
    assert EasyTer.terminal_key_sequence(
        Qt.Key_unknown, False, False, False, "م", kitty=True) == "م"
    # Shift alone (a different Arabic form) is still text, not a shortcut
    event = _key(
        Qt.Key_unknown, Qt.ShiftModifier,
        text="إ", scan=_SCAN["H"], vk=_VK["H"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=True)
    assert key == int(Qt.Key_unknown) and altgr is None
    assert EasyTer.terminal_key_sequence(
        key, False, False, True, "إ", kitty=False) == "إ"


def test_non_arabic_layout_does_not_remap():
    event = _key(
        Qt.Key_unknown, Qt.ControlModifier,
        text="ؤ", scan=_SCAN["C"], vk=_VK["C"])
    key, altgr = EasyTer.resolve_layout_key(event, arabic_layout=False)
    assert key == int(Qt.Key_unknown) and altgr is None


def test_arabic_language_id(monkeypatch):
    assert EasyTer.keyboard_layout_is_arabic(0x0401) is True   # ar-SA
    assert EasyTer.keyboard_layout_is_arabic(0x0801) is True   # ar-IQ
    assert EasyTer.keyboard_layout_is_arabic(0x0409) is False  # en-US
    assert EasyTer.keyboard_layout_is_arabic(0x040C) is False  # fr-FR
    assert EasyTer.keyboard_layout_is_arabic(0) is False
    monkeypatch.setattr(EasyTer.sys, "platform", "linux")
    assert EasyTer._current_keyboard_hkl() is None
    assert EasyTer.keyboard_layout_is_arabic() is False


def test_keyboard_layout_probe_does_not_raise():
    hkl = EasyTer._current_keyboard_hkl()
    assert hkl is None or isinstance(hkl, int)
    assert isinstance(EasyTer.keyboard_layout_is_arabic(), bool)
