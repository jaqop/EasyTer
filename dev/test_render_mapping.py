"""Regression tests for two fixes:

  restore_command()  - the session-restore auto-run guard. easyter_session.json is a
      plain user-writable file whose `command` is passed straight to the pseudo-console
      at startup, so a tampered file could otherwise auto-run an arbitrary program on the
      next launch. Only an exact match against an offered shell is allowed.

  wide-char column mapping - QTextLayout's xToCursor/cursorToX count UTF-16 code units,
      but the terminal grid counts pyte columns. A wide char (CJK = 1 UTF-16 unit but 2
      grid columns; astral emoji = 2 units) makes the two diverge, so the block cursor,
      mouse hit-testing, and selection highlight all drifted on any such line. _draw_row
      now records a per-row pos2col table (UTF-16 offset -> pyte column) and translates
      through it. These tests pin both directions so the drift can't silently regress.

Run:  python -m unittest test_render_mapping
      (needs PySide6/pyte/pywinpty; skipped automatically if they're missing)
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import EasyTer as E
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QPointF
    _app = QApplication.instance() or QApplication(["test"])
except Exception as _e:            # GUI deps missing in this env - skip, don't fail
    E = None
    _import_error = _e


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class RestoreCommandTest(unittest.TestCase):
    """restore_command() only lets an exact, offered shell through."""

    def test_known_bare_shells_pass(self):
        for cmd in ("powershell.exe", "cmd.exe"):
            self.assertEqual(E.restore_command(cmd), cmd)

    def test_case_insensitive(self):
        self.assertEqual(E.restore_command("PowerShell.EXE"), "PowerShell.EXE")

    def test_argv_list_rejected(self):
        # the classic payload: a valid shell exe with malicious trailing args
        self.assertEqual(E.restore_command(["cmd.exe", "/c", "calc"]), E.DEFAULT_SHELL)

    def test_args_in_string_rejected(self):
        self.assertEqual(E.restore_command("cmd.exe /c calc"), E.DEFAULT_SHELL)

    def test_unknown_exe_rejected(self):
        self.assertEqual(E.restore_command("C:/evil/payload.exe"), E.DEFAULT_SHELL)

    def test_non_string_rejected(self):
        for bad in (None, {"x": 1}, 42, ["cmd.exe"]):
            self.assertEqual(E.restore_command(bad), E.DEFAULT_SHELL)


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class WideCharColumnMappingTest(unittest.TestCase):
    """A BMP wide char (CJK) occupies 1 UTF-16 unit but 2 grid columns - the case
    where layout position and pyte column truly diverge - so we use it as the probe."""

    def setUp(self):
        self.tw = E.TerminalWidget(command="cmd.exe")
        self.tw.resize(1200, 700)
        b = self.tw.backend
        with b.lock:
            b.stream.feed("\x1b[2J\x1b[H")     # clear + home
            b.stream.feed("中ABCDEF")           # CJK at cols 0-1, then ABCDEF at cols 2..7
        # paint offscreen so _draw_row runs and fills _row_pos2col / _row_layouts
        img = QImage(self.tw.width(), self.tw.height(), QImage.Format_ARGB32)
        p = QPainter(img)
        self.tw._paint(p)
        p.end()
        self.p2c = self.tw._row_pos2col.get(0)
        self.line = self.tw._row_layouts.get(0)[1]

    def _x_of_offset(self, off):
        rx = self.line.cursorToX(off)
        return rx[0] if isinstance(rx, (tuple, list)) else rx

    def test_pos2col_prefix(self):
        # UTF-16 offsets 0=中,1=A,2=B,...  columns: 中 spans 0-1, so A=2, B=3, ...
        # (the row is full-width, so the table continues into trailing spaces past F)
        self.assertEqual(self.p2c[:8], [0, 2, 3, 4, 5, 6, 7, 8])

    def test_click_maps_to_pyte_column(self):
        # click clearly inside each glyph box; expect the PYTE column, not the raw offset
        for name, off, expect_col in [("A", 1, 2), ("B", 2, 3), ("F", 6, 7)]:
            x0, x1 = self._x_of_offset(off), self._x_of_offset(off + 1)
            cx = x0 + 0.25 * (x1 - x0)
            _, col = self.tw._pos_to_cell(QPointF(cx, self.tw.ch / 2))
            self.assertEqual(col, expect_col, f"click over {name!r} -> col {col}")
            self.assertNotEqual(col, off, f"{name!r} must differ from raw offset {off}")

    def test_cursor_x_uses_correct_offset(self):
        # cursor sits at col 8 (中=2 + ABCDEF=6); must map col 8 -> offset 7 before cursorToX
        with self.tw.backend.lock:
            cur_x = self.tw.backend.screen.cursor.x
        self.assertEqual(cur_x, 8)
        rx = self.tw._col_to_x(self.line, self.p2c, cur_x)
        self.assertAlmostEqual(rx, self._x_of_offset(7), delta=0.5)

    def test_middle_column_divergence(self):
        # pyte col 3 ('B') must resolve to offset 2, not the old-bug offset 3 ('C')
        rx = self.tw._col_to_x(self.line, self.p2c, 3)
        self.assertAlmostEqual(rx, self._x_of_offset(2), delta=0.5)
        self.assertGreater(abs(self._x_of_offset(2) - self._x_of_offset(3)), 0.5)

    def test_selection_text_round_trip(self):
        self.tw.sel_anchor = (self.tw._paint_start, 2)
        self.tw.sel_point = (self.tw._paint_start, 8)
        self.assertEqual(self.tw._selection_text(), "ABCDEF")


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class BlankLineBackgroundTest(unittest.TestCase):
    """A blank line carrying a non-default background must still be drawn, not skipped."""

    def _paint_first_row(self, feed):
        tw = E.TerminalWidget(command="cmd.exe")
        tw.resize(1200, 700)
        b = tw.backend
        with b.lock:
            b.stream.feed("\x1b[2J\x1b[H")
            b.stream.feed(feed)
        img = QImage(tw.width(), tw.height(), QImage.Format_ARGB32)
        p = QPainter(img)
        tw._paint(p)
        p.end()
        return tw

    def test_bg_is_default_helper(self):
        self.assertTrue(E._bg_is_default(("default", "default", False, False)))
        self.assertFalse(E._bg_is_default(("default", "0000ff", False, False)))  # blue bg
        # reverse video turns a bright foreground into the visible background
        self.assertFalse(E._bg_is_default(("ffffff", "default", False, True)))

    def test_default_blank_line_is_skipped(self):
        tw = self._paint_first_row("")                       # empty row
        self.assertIsNone(tw._row_layouts.get(0))

    def test_colored_blank_line_is_drawn(self):
        # three spaces on a truecolor-blue background, then reset
        tw = self._paint_first_row("\x1b[48;2;0;0;255m   \x1b[0m")
        self.assertIsNotNone(tw._row_layouts.get(0),
                             "blank line with a colored background must be drawn")


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class SearchDebounceTest(unittest.TestCase):
    def setUp(self):
        self.tw = E.TerminalWidget(command="cmd.exe")
        self.tw.resize(1200, 700)
        with self.tw.backend.lock:
            self.tw.backend.stream.feed("\x1b[2J\x1b[Hhello world\r\n")

    def test_empty_term_clears_immediately(self):
        self.tw.search_matches = [1, 2, 3]
        self.tw._schedule_search("")
        self.assertFalse(self.tw._search_timer.isActive())
        self.assertEqual(self.tw.search_matches, [])

    def test_nonempty_term_is_deferred(self):
        self.tw.search_matches = []
        self.tw._schedule_search("hello")
        # search has NOT run yet - it waits for the debounce timer
        self.assertTrue(self.tw._search_timer.isActive())
        self.assertEqual(self.tw._pending_search, "hello")
        self.assertEqual(self.tw.search_matches, [])
        # when the timer fires (invoke its effect directly) the scan runs
        self.tw._do_search(self.tw._pending_search)
        self.assertTrue(self.tw.search_matches, "the deferred scan should find 'hello'")


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class BackendReleaseTest(unittest.TestCase):
    """A shell that exits on its own must release the pseudo-console, not linger."""

    def test_release_marks_dead_and_nulls_proc(self):
        tw = E.TerminalWidget(command="cmd.exe")
        b = tw.backend
        self.assertTrue(b._alive)
        self.assertIsNotNone(b.proc)
        b._release()
        self.assertFalse(b._alive)
        self.assertIsNone(b.proc)

    def test_release_is_idempotent(self):
        b = E.TerminalWidget(command="cmd.exe").backend
        b._release()
        b._release()   # must not raise on the second call (proc already None)
        self.assertIsNone(b.proc)

    def test_close_delegates_to_release(self):
        b = E.TerminalWidget(command="cmd.exe").backend
        b.close()
        self.assertFalse(b._alive)
        self.assertIsNone(b.proc)

    def test_write_after_release_is_noop(self):
        b = E.TerminalWidget(command="cmd.exe").backend
        b._release()
        b.write("echo hi\r")   # guarded by _alive / proc-is-None: must not raise


@unittest.skipIf(E is None, "EasyTer import failed (GUI deps missing)")
class ReaderResilienceTest(unittest.TestCase):
    """A malformed chunk must not kill the reader thread (which would freeze the pane)."""

    def _screen_has(self, b, token):
        with b.lock:
            return token in "\n".join(b.screen.display)

    def _wait_for(self, b, token, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._screen_has(b, token):
                return True
            time.sleep(0.05)
        return False

    def test_reader_survives_a_feed_exception(self):
        tw = E.TerminalWidget(command="cmd.exe")
        b = tw.backend
        self.addCleanup(b.close)
        # inject a one-time failure the first time a chunk carrying the token is fed
        orig = b._feed_with_marks
        state = {"boomed": False}

        def patched(data):
            if not state["boomed"] and "BOOMTOKEN" in data:
                state["boomed"] = True
                raise RuntimeError("injected feed failure")
            return orig(data)

        b._feed_with_marks = patched
        # let the shell reach its prompt, then trigger the failure and follow-up output
        self.assertTrue(self._wait_for(b, ">", timeout=8.0), "cmd never reached a prompt")
        b.write("echo BOOMTOKEN\r")
        self.assertTrue(self._wait_for(b, "BOOMTOKEN", timeout=8.0))
        self.assertTrue(state["boomed"], "the injected feed failure never fired")
        # the reader must have recovered and still be processing subsequent output
        b.write("echo AFTERTOKEN\r")
        self.assertTrue(self._wait_for(b, "AFTERTOKEN", timeout=8.0),
                        "reader died on the bad chunk (pane would be frozen)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
