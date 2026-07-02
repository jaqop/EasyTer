# -*- coding: utf-8 -*-
"""Regression test: switching shells must not kill pane input.

Root cause (fixed 2026-07-02): in restart_with(), `self.backend.disconnect()`
raises TypeError in PySide6 (QObject.disconnect() needs args) and was swallowed,
so the OLD backend's `exited` signal stayed connected. When close() ended the old
reader thread it emitted `exited`, which fired _on_exit AFTER the new backend
started, setting _exited=True and blocking keyPressEvent forever (pane needed
reopening). This test mirrors restart_with/_on_exit and asserts the stale signal
can no longer mark the pane exited.
"""
from PySide6.QtCore import QObject, Signal


class FakeBackend(QObject):
    # same signals _start_backend connects to
    data_ready = Signal()
    exited = Signal()
    alt_screen_changed = Signal(bool)
    command_ended = Signal(int)
    clipboard_set = Signal(str)
    cwd_changed = Signal(str)
    cmd_changed = Signal()
    edit_file = Signal(str)


class FakePane(QObject):
    """Mirrors the relevant TerminalWidget logic (no Qt widget / no real PTY)."""
    def __init__(self):
        super().__init__()
        self._exited = False
        self.backend = None

    def _start_backend(self):
        self.backend = FakeBackend()
        self.backend.exited.connect(self._on_exit)
        self.backend.clipboard_set.connect(lambda txt: None)  # lambda, like the real one
        self._exited = False

    def _on_exit(self):
        # the fix: ignore a stale 'exited' from a previous backend
        if self.sender() is not None and self.sender() is not self.backend:
            return
        self._exited = True

    def restart_with(self):
        old = self.backend
        # the fix: disconnect each signal explicitly (was self.backend.disconnect())
        for _sig in ("data_ready", "exited", "alt_screen_changed", "command_ended",
                     "clipboard_set", "cwd_changed", "cmd_changed", "edit_file"):
            try:
                getattr(old, _sig).disconnect()
            except Exception:
                pass
        self._start_backend()
        return old


def test_stale_exit_does_not_kill_input():
    pane = FakePane()
    pane._start_backend()
    old = pane.restart_with()          # user switches shell
    old.exited.emit()                  # dying old reader thread fires exited
    assert pane._exited is False, "stale exited killed input (regression!)"


def test_real_exit_still_marks_pane():
    pane = FakePane()
    pane._start_backend()
    pane.backend.exited.emit()         # the CURRENT shell genuinely exits
    assert pane._exited is True, "real exit must still mark the pane exited"


if __name__ == "__main__":
    test_stale_exit_does_not_kill_input()
    test_real_exit_still_marks_pane()
    print("✅ both tests passed: shell switch keeps input; real exit still marks exited")
