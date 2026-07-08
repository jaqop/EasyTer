"""Tests for the terminal-wg BiDi escape sequences (BDSM / SCP).

EasyTer's grid engine (visual->logical Arabic restoration) was historically
enabled only by the cmd_is_claude() process-name heuristic. The freedesktop
terminal-wg recommendation defines standard escapes for the same contract:

  BDSM  CSI 8 h / CSI 8 l   implicit (logical order) / explicit (visual order)
  SCP   CSI Pn SP k         paragraph direction: 0=default, 1=LTR, 2=RTL

scan_bidi_modes() detects them in the raw output stream; an app that sends
CSI 8 l gets the grid engine with no heuristic involved. These tests pin the
scanner and the SCP override in restore_bidi_line().

Run:  python -m unittest dev.test_bidi_modes
"""
import unittest

try:
    from EasyTer import scan_bidi_modes, restore_bidi_line
except Exception:     # PySide6/pywinpty missing in this env - skip, don't fail
    scan_bidi_modes = None


@unittest.skipIf(scan_bidi_modes is None, "EasyTer import failed (GUI deps missing)")
class ScanBidiModesTest(unittest.TestCase):
    def test_no_sequences_keeps_state(self):
        self.assertEqual(scan_bidi_modes("plain output", False, None)[:2],
                         (False, None))
        self.assertEqual(scan_bidi_modes("plain output", True, True)[:2],
                         (True, True))

    def test_bdsm_explicit_and_implicit(self):
        ex, base, pos = scan_bidi_modes("x\x1b[8ly", False, None)
        self.assertTrue(ex)
        self.assertEqual(pos, 1)
        ex, _, _ = scan_bidi_modes("x\x1b[8hy", True, None)
        self.assertFalse(ex)

    def test_last_bdsm_wins(self):
        ex, _, _ = scan_bidi_modes("\x1b[8l...\x1b[8h", False, None)
        self.assertFalse(ex)
        ex, _, _ = scan_bidi_modes("\x1b[8h...\x1b[8l", False, None)
        self.assertTrue(ex)

    def test_scp_directions(self):
        self.assertEqual(scan_bidi_modes("\x1b[1 k", False, None)[1], False)  # LTR
        self.assertEqual(scan_bidi_modes("\x1b[2 k", False, None)[1], True)   # RTL
        self.assertIsNone(scan_bidi_modes("\x1b[0 k", False, True)[1])   # default
        self.assertIsNone(scan_bidi_modes("\x1b[ k", False, True)[1])    # omitted

    def test_last_scp_wins(self):
        _, base, _ = scan_bidi_modes("\x1b[2 k...\x1b[1 k", False, None)
        self.assertEqual(base, False)

    def test_private_modes_do_not_false_match(self):
        # DECARM (CSI ? 8 h) and alt-screen (CSI ? 1049 l) must not read as BDSM
        ex, base, pos = scan_bidi_modes("\x1b[?8h\x1b[?1049l\x1b[?2004h", False, None)
        self.assertEqual((ex, base, pos), (False, None, -1))

    def test_position_reported_for_reset_ordering(self):
        # the caller compares this position against prompt/alt-exit markers
        data = "\x1b[8l" + "output" * 3
        self.assertEqual(scan_bidi_modes(data, False, None)[2], 0)
        self.assertEqual(scan_bidi_modes("no match", False, None)[2], -1)


@unittest.skipIf(scan_bidi_modes is None, "EasyTer import failed (GUI deps missing)")
class ScpOverrideTest(unittest.TestCase):
    # visual-order Arabic sample: logical "سلام" stored reversed by the app
    VISUAL_ARABIC = "سلام"[::-1]

    def test_autodetect_unchanged(self):
        # None = per-line autodetection (the pre-SCP behaviour)
        self.assertEqual(restore_bidi_line(self.VISUAL_ARABIC),
                         restore_bidi_line(self.VISUAL_ARABIC, None))

    def test_forced_rtl_reverses_whole_line(self):
        self.assertEqual(restore_bidi_line(self.VISUAL_ARABIC, True), "سلام")

    def test_forced_ltr_only_reverses_arabic_runs(self):
        line = "abc " + self.VISUAL_ARABIC
        self.assertEqual(restore_bidi_line(line, False), "abc سلام")

    def test_pure_english_autodetect_untouched(self):
        self.assertIsNone(restore_bidi_line("just english", None))
        self.assertIsNone(restore_bidi_line("just english", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
