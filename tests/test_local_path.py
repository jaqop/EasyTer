# -*- coding: utf-8 -*-
"""NTLM gate: untrusted terminal paths must not reach the filesystem.

The pure cases import easyterpro.localpath only, so they do not need a
console. Sink cases import EasyTer and run on the Windows CI job.
"""

import json
import ntpath
import os

import pytest

from easyterpro.localpath import accept_local_path, osc7_host_ok

# Every form the gate is required to reject. Parametrized once below, and
# walked again by each sink so a regression that skips the gate fails there.
REJECTED = [
    # UNC
    r"\\host\share",
    r"\\host",
    r"\\host\share\a.txt",
    r"//host/share",
    r"//host/share/a.txt",
    r"//host",
    r"\\?\C:\Users\x",
    r"\\?\UNC\host\share",
    r"\\?\unc\host\share",
    r"//?/UNC/host/share",
    r"\\.\C:\Users\x",
    r"\\.\UNC\host\share",
    r"//./UNC/host/share",
    r"\\.\pipe\evil",
    r"\\.\COM1",
    r"\??\C:\Users\x",
    r"\??\UNC\host\share",
    r"/??/C:/Users/x",
    r"\\host@SSL\share",
    r"\\host@SSL\share\a.txt",
    r"\\host@8080\share",
    r"\\host@SSL@443\DavWWWRoot",
    r"\\host@SSL@443\DavWWWRoot\file.txt",
    r"\\host@ssl\share",
    "file://///host/share",
    "file://///host/share/a.txt",
    "FILE://///host/share",
    "file:////host/share",
    r"file:\\\\\host\share",
    # mixed separators
    r"C:\Users/x",
    r"C:/Users\x",
    r"\\host/share",
    r"//host\share",
    r"C:\Users\x/",
    # percent-encoded separators and double encoding
    r"%5C%5Chost%5Cshare",
    r"%2F%2Fhost%2Fshare",
    r"%255C%255Chost%255Cshare",
    r"C:\Users%2Fx",
    r"C:/Users%5Cx",
    r"file%3A%2F%2F%2F%2F%2Fhost%2Fshare",
    r"C:\a%22b",
    r"C:\a%2Cb",
    # NFKC / fullwidth / small solidus
    "\uFF3C\uFF3Chost\uFF3Cshare",
    "\uFF0F\uFF0Fhost\uFF0Fshare",
    "C:\\Users\uFF0Fx",
    "\uFE68\uFE68host\uFE68share",
    "file:\uFF0F\uFF0F\uFF0F\uFF0F\uFF0Fhost/share",
    "C:\\NUL\uFF0Etxt",
    "C:\\COM\uFF11",
    "C:\\foo\uFF1Abar",
    # control and bidi
    "C:\\Users\\x\n",
    "C:\\Users\\x\r\n",
    "C:\\Users\\x\tfile",
    "C:\\Users\\x\x00y",
    "C:\\Users\\x\x1by",
    "C:\\Users\\x\x7fy",
    "C:\\Users\\x\u202ey",
    "\u202e\\\\host\\share",
    "\u200fC:\\Users\\x",
    "\u200eC:\\Users\\x",
    "C:\\Users\\x\u2066y",
    "C:\\Users\\x\u2067y",
    "C:\\Users\\x\u2068y",
    "C:\\Users\\x\u2069y",
    "C:\\Users\\x\u202ay",
    "C:\\Users\\x\u202by",
    "C:\\Users\\x\u202cy",
    "C:\\Users\\x\u202dy",
    "C:\\Users\\x\u061cy",
    # alternate data streams
    r"C:\foo:bar",
    r"C:\Users\x\a.txt:stream",
    r"C:\Users\x\a.txt::$DATA",
    r"C:\foo:bar\..\..\Users",
    # DOS devices, including extension / trailing dot / space forms
    r"C:\CON",
    r"C:\NUL",
    r"C:\PRN",
    r"C:\AUX",
    r"C:\foo\NUL.txt",
    r"C:\foo\con.txt",
    r"C:\nul.",
    r"C:\foo\COM1.dat",
    r"c:\aux",
    r"C:\CON.",
    r"C:\CON .txt",
    r"C:\NUL\..\Users",
    r"C:\CONIN$",
    r"C:\CONOUT$",
    r"C:\CLOCK$",
    r"C:\foo\CONIN$.txt",
    r"C:\foo\CONOUT$.txt",
    r"C:\CLOCK$.txt",
    # quotes and commas
    r"C:\foo,bar\a.txt",
    'C:\\foo"bar\\a.txt',
    # not a drive-absolute path
    "",
    "   ",
    r"Users\x",
    r"src\app.py",
    "C:foo",
    r"C:foo\bar",
    r"\Windows",
    "/Windows",
    "..",
    ".",
    r"\\localhost\C$\Users",
    "//localhost/C$/Users",
    r"  \\host\share",
]
REJECTED += [rf"C:\COM{n}" for n in range(0, 10)]
REJECTED += [rf"C:\LPT{n}" for n in range(0, 10)]
REJECTED += [rf"C:\foo\COM{n}.txt" for n in range(1, 10)]
REJECTED += [rf"C:\foo\LPT{n}.txt" for n in range(1, 10)]

ACCEPTED = [
    (r"C:\Users\x", r"C:\Users\x"),
    (r"D:\proj", r"D:\proj"),
    ("D:\\proj\\\u0645\u0634\u0631\u0648\u0639", "D:\\proj\\\u0645\u0634\u0631\u0648\u0639"),
    ("D:\\\u0645\u0634\u0627\u0631\u064a\u0639\\\u0645\u0644\u0641",
     "D:\\\u0645\u0634\u0627\u0631\u064a\u0639\\\u0645\u0644\u0641"),
    (r"C:\Users\My Documents\a.txt", r"C:\Users\My Documents\a.txt"),
    (r"C:/Users/x", r"C:\Users\x"),
    (r"C:\Users\x\\", r"C:\Users\x"),
    (r"C:\Users\.\x", r"C:\Users\x"),
    (r"C:\Users\x\..\y", r"C:\Users\y"),
    (r"c:\users\x", r"c:\users\x"),
    (r"C:\Users\CONSOLE\x", r"C:\Users\CONSOLE\x"),
    (r"C:\Users\COM10\x", r"C:\Users\COM10\x"),
    (r"C:\Users\LPT10\x", r"C:\Users\LPT10\x"),
    (r"C:\100%done", r"C:\100%done"),
    ("C:\\", "C:\\"),
    ("C:\\A&B\\a.txt", "C:\\A&B\\a.txt"),
]

BAD_HOSTS = [
    "evil.example",
    "wsl.local",
    "127.0.0.1",
    "localhost.localdomain",
    "localhost.",
    "user@localhost",
    "[::1]",
    "LOCALHOST.localdomain",
    "localhost:80",
]
GOOD_HOSTS = ["", "localhost", "LOCALHOST", "LocalHost", "  localhost  "]


def _case_id(value):
    if not isinstance(value, str):
        return type(value).__name__
    return value.encode("unicode_escape").decode("ascii")


def _uncish(path):
    if isinstance(path, bytes):
        path = path.decode("utf-8", "replace")
    elif not isinstance(path, str):
        path = os.fspath(path)
    folded = path.replace("/", "\\")
    low = folded.lower()
    return folded.startswith("\\\\") or low.startswith("\\??\\") or low.startswith("file:")


def _osc_embeddable(path):
    return isinstance(path, str) and "\x07" not in path and "\x1b" not in path and '"' not in path


def install_guard(monkeypatch):
    """Record filesystem calls and refuse to perform them for a UNC-like path."""
    calls = []
    real_stat = os.stat
    real_isdir = os.path.isdir
    real_exists = os.path.exists
    real_isfile = os.path.isfile
    real_open = open

    def record(kind, path):
        text = path.decode("utf-8", "replace") if isinstance(path, bytes) else os.fspath(path)
        calls.append((kind, text))
        if _uncish(text):
            raise OSError(2, "unc blocked", text)

    def stat(path, *args, **kwargs):
        record("stat", path)
        return real_stat(path, *args, **kwargs)

    def isdir(path):
        record("isdir", path)
        return real_isdir(path)

    def exists(path):
        record("exists", path)
        return real_exists(path)

    def isfile(path):
        record("isfile", path)
        return real_isfile(path)

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            record("open", file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(os.path, "isdir", isdir)
    monkeypatch.setattr(os.path, "exists", exists)
    monkeypatch.setattr(os.path, "isfile", isfile)
    monkeypatch.setattr("builtins.open", guarded_open)
    return calls


def assert_no_unc(calls):
    bad = [(kind, path) for kind, path in calls if _uncish(path)]
    assert bad == []


class _Sig:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


def _backend(easyter):
    backend = easyter.PtyBackend.__new__(easyter.PtyBackend)
    backend.cwd = None
    backend.cwd_changed = _Sig()
    backend.edit_file = _Sig()
    return backend


@pytest.mark.parametrize("path", REJECTED, ids=_case_id)
def test_accept_local_path_rejects(path):
    assert accept_local_path(path) is None


@pytest.mark.parametrize("path", [None, 12, b"C:\\Users\\x", ["C:\\Users\\x"]], ids=_case_id)
def test_accept_local_path_rejects_non_strings(path):
    assert accept_local_path(path) is None


@pytest.mark.parametrize("path,expected", ACCEPTED, ids=[_case_id(p) for p, _e in ACCEPTED])
def test_accept_local_path_accepts(path, expected):
    assert accept_local_path(path) == expected


def test_gate_does_not_touch_the_filesystem():
    originals = (os.stat, os.path.isdir, os.path.exists, os.path.isfile)

    def boom(*_args, **_kwargs):
        raise AssertionError("filesystem call")

    try:
        os.stat = boom
        os.path.isdir = boom
        os.path.exists = boom
        os.path.isfile = boom
        for path in REJECTED:
            assert accept_local_path(path) is None
        for path, expected in ACCEPTED:
            assert accept_local_path(path) == expected
    finally:
        os.stat, os.path.isdir, os.path.exists, os.path.isfile = originals


@pytest.mark.parametrize("host", GOOD_HOSTS)
def test_osc7_host_allowed(host):
    assert osc7_host_ok(host) is True


@pytest.mark.parametrize("host", BAD_HOSTS)
def test_osc7_host_rejected(host):
    assert osc7_host_ok(host) is False


def test_osc7_host_rejects_non_strings():
    assert osc7_host_ok(None) is False
    assert osc7_host_ok(b"localhost") is False


def test_osc99_rejected_paths_never_stat(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    backend = _backend(EasyTer)
    backend.cwd = r"C:\keep"
    checked = 0
    for path in REJECTED:
        if not _osc_embeddable(path):
            continue
        del calls[:]
        backend._scan_cwd("\x1b]9;9;" + path + "\x07")
        assert backend.cwd == r"C:\keep", path
        assert calls == [], (path, calls)
        checked += 1
    assert checked > 20


def test_osc99_local_path_is_stored_only_after_isdir(monkeypatch):
    import EasyTer
    seen = []

    def isdir(path):
        seen.append(path)
        return path == r"C:\Users\x"

    monkeypatch.setattr(os.path, "isdir", isdir)
    backend = _backend(EasyTer)
    backend._scan_cwd('\x1b]9;9;"C:\\Users\\x"\x07')
    assert seen == [r"C:\Users\x"]
    assert backend.cwd == r"C:\Users\x"
    assert backend.cwd_changed.emitted == [(r"C:\Users\x",)]
    # a rejected report afterwards must not replace it or stat a UNC path
    backend._scan_cwd("\x1b]9;9;\\\\evil\\share\x07")
    assert backend.cwd == r"C:\Users\x"
    assert seen == [r"C:\Users\x"]


def test_osc7_bad_host_never_stats(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    backend = _backend(EasyTer)
    backend.cwd = r"C:\keep"
    for host in BAD_HOSTS:
        del calls[:]
        data = "\x1b]7;file://" + host + "/C:/Users/me\x07"
        backend._scan_cwd(data)
        assert backend.cwd == r"C:\keep", host
        assert calls == [], (host, calls)
    del calls[:]
    backend._scan_cwd("\x1b]7;file://localhost//evil/share/a.txt\x07")
    assert backend.cwd == r"C:\keep"
    assert calls == []


def test_osc7_localhost_path_reaches_isdir_normalized(monkeypatch):
    import EasyTer
    seen = []

    def isdir(path):
        seen.append(path)
        return True

    monkeypatch.setattr(os.path, "isdir", isdir)
    backend = _backend(EasyTer)
    backend._scan_cwd("\x1b]7;file://localhost/C:/Users/me/My%20Documents\x07")
    assert seen == [r"C:\Users\me\My Documents"]
    assert backend.cwd == r"C:\Users\me\My Documents"
    del seen[:]
    backend._scan_cwd("\x1b]7;file:///D:/proj\x07")
    assert seen == [r"D:\proj"]
    assert backend.cwd == r"D:\proj"


def test_osc6969_rejected_paths_are_not_emitted(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    backend = _backend(EasyTer)
    checked = 0
    for path in REJECTED:
        if not isinstance(path, str) or "\x07" in path or "\x1b" in path:
            continue
        del calls[:]
        backend.edit_file.emitted.clear()
        backend._scan_edit("\x1b]6969;" + path + "\x07")
        assert backend.edit_file.emitted == [], path
        assert calls == [], (path, calls)
        checked += 1
    assert checked > 20


def test_osc6969_accepted_path_is_emitted_without_stat(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    backend = _backend(EasyTer)
    backend._scan_edit("\x1b]6969;D:\\proj\\\u0645\u0634\u0631\u0648\u0639\\a.txt\x07")
    assert backend.edit_file.emitted == [("D:\\proj\\\u0645\u0634\u0631\u0648\u0639\\a.txt",)]
    assert calls == []


def test_on_edit_file_rejected_skips_dialog_and_filesystem(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    asked = []
    monkeypatch.setattr(EasyTer, "confirm_local_open", lambda *_a, **_k: asked.append(1) or True)
    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)

    def _no_session():
        raise AssertionError("session looked up for a rejected path")

    widget._session = _no_session
    for path in (r"\\evil\share\a.txt", r"//evil/share/a.txt", r"\\?\UNC\evil\share\a.txt"):
        del calls[:]
        widget._on_edit_file(path)
        assert calls == [], (path, calls)
    assert asked == []


def test_on_edit_file_cancel_does_not_open(qapp, monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
    widget._session = lambda: (_ for _ in ()).throw(AssertionError("opened"))
    monkeypatch.setattr(EasyTer, "confirm_local_open", lambda _parent, path: False)
    widget._on_edit_file(r"C:\Users\x\a.txt")
    assert calls == []


def test_on_edit_file_confirm_opens_the_exact_path(qapp, tmp_path, monkeypatch):
    import EasyTer
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    accepted = accept_local_path(str(target))
    assert accepted
    asked = []

    def confirm(_parent, path):
        asked.append(path)
        return True

    monkeypatch.setattr(EasyTer, "confirm_local_open", confirm)
    editor = EasyTer.EditorWidget()

    class _Session:
        def findChildren(self, _cls):
            return [editor]

    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
    widget._session = lambda: _Session()
    widget._on_edit_file(str(target))
    assert asked == [accepted]
    assert editor.path == accepted
    assert editor.edit.toPlainText() == "hello"


def test_confirm_dialog_shows_the_exact_path(qapp, monkeypatch):
    import EasyTer
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    shown = {}
    path = "D:\\proj\\\u0645\u0634\u0631\u0648\u0639\\a&b.txt"

    class _Box:
        # The dialog reads these off the same class it constructs.
        Question = QMessageBox.Question
        Ok = QMessageBox.Ok
        Cancel = QMessageBox.Cancel

        def __init__(self, parent=None):
            shown["parent"] = parent

        def setTextFormat(self, fmt):
            shown["format"] = fmt

        def setIcon(self, _icon):
            return None

        def setWindowTitle(self, text):
            shown["title"] = text

        def setText(self, text):
            shown["text"] = text

        def setInformativeText(self, text):
            shown["info"] = text

        def setStandardButtons(self, _buttons):
            return None

        def setDefaultButton(self, button):
            shown["default"] = button

        def exec(self):
            return QMessageBox.Cancel

    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox", _Box)
    assert EasyTer.confirm_local_open(None, path) is False
    assert shown["text"] == path
    assert shown["format"] == Qt.PlainText
    assert shown["default"] == QMessageBox.Cancel
    assert shown["title"] == "Open this file?"
    assert "trust" in shown["info"]


def test_load_file_and_save_never_touch_a_rejected_path(qapp, monkeypatch):
    import EasyTer
    editor = EasyTer.EditorWidget()
    calls = install_guard(monkeypatch)
    for path in REJECTED:
        del calls[:]
        editor.load_file(path)
        assert editor.path is None
        assert calls == [], (path, calls)
    editor.path = r"\\evil\share\secret.txt"
    editor.edit.setPlainText("nope")
    del calls[:]
    editor.save()
    assert calls == []
    assert editor.path is None


def test_session_does_not_store_or_reopen_a_rejected_path(qapp, monkeypatch, tmp_path):
    import EasyTer
    editor = EasyTer.EditorWidget()
    editor.path = r"\\host\share\secret.txt"
    calls = install_guard(monkeypatch)
    node = EasyTer.serialize_node(editor)
    assert node["path"] is None
    blob = json.dumps(node)
    assert "host" not in blob
    assert "secret" not in blob
    assert_no_unc(calls)
    restored = EasyTer.build_node({"type": "editor", "path": r"\\host\share\secret.txt"})
    assert restored.path is None
    assert_no_unc(calls)

    target = tmp_path / "kept.txt"
    target.write_text("kept", encoding="utf-8")
    accepted = accept_local_path(str(target))
    editor.path = accepted
    stored = EasyTer.serialize_node(editor)
    assert stored["path"] == accepted
    again = EasyTer.build_node(stored)
    assert again.path == accepted
    assert again.edit.toPlainText() == "kept"


def test_click_resolution_never_stats_a_rejected_path(monkeypatch):
    import EasyTer
    seen = []

    def isfile(path):
        seen.append(path)
        if _uncish(path):
            raise AssertionError(path)
        return True

    monkeypatch.setattr(os.path, "isfile", isfile)
    monkeypatch.setattr(os, "stat", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("stat")))
    for path in REJECTED:
        # A relative reference joined onto a local cwd may become a local
        # path. It must never become a UNC path, and isfile stays uncalled.
        resolved = EasyTer.resolve_click_path(path, r"C:\proj")
        assert resolved is None or (not _uncish(resolved) and accept_local_path(resolved) == resolved), path
        from_bad_cwd = EasyTer.resolve_click_path("a.txt", path)
        assert from_bad_cwd is None or not _uncish(from_bad_cwd), path
    assert seen == []
    assert EasyTer.resolve_click_path("a.txt", r"C:\proj") == r"C:\proj\a.txt"
    assert EasyTer.resolve_click_path(r"sub\a.txt", r"C:\proj") == r"C:\proj\sub\a.txt"
    assert EasyTer.resolve_click_path(r"..\a.txt", r"C:\proj\sub") == r"C:\proj\a.txt"
    assert os.path.isfile(r"C:\proj\a.txt") is True
    assert seen == [r"C:\proj\a.txt"]


def test_start_dir_never_stats_a_rejected_path(monkeypatch):
    import EasyTer
    calls = install_guard(monkeypatch)
    monkeypatch.setitem(EasyTer.SETTINGS, "start_dir", r"\\evil\settings")
    monkeypatch.setattr(os.path, "expanduser", lambda _p: r"\\evil\home")
    got = EasyTer.resolve_start_dir(r"\\evil\cwd")
    assert got == EasyTer._drive_root_fallback()
    assert accept_local_path(got) == got
    assert_no_unc(calls)
    for path in REJECTED:
        assert EasyTer.existing_local_dir(path) is None


def test_argv_never_stats_a_rejected_path(monkeypatch):
    import EasyTer
    seen = []

    def isdir(path):
        seen.append(path)
        if _uncish(path):
            raise AssertionError(path)
        return path == r"C:\work"

    monkeypatch.setattr(os.path, "isdir", isdir)
    assert EasyTer.start_dir_from_argv([r"\\evil\share", "//evil/share", r"\\?\UNC\evil\share"]) is None
    assert seen == []
    assert EasyTer.start_dir_from_argv([r"\\evil\share", r"C:\work"]) == r"C:\work"
    assert seen == [r"C:\work"]
    for path in REJECTED:
        if not isinstance(path, str) or not path.strip():
            continue
        before = len(seen)
        result = EasyTer.start_dir_from_argv([path])
        fresh = seen[before:]
        assert all(not _uncish(item) for item in fresh), (path, fresh)
        # absolute rejects are not joined onto the cwd, so isdir is not called
        if ntpath.isabs(path):
            assert fresh == [], (path, fresh)
            assert result is None


def test_gate_keeps_the_original_spelling():
    ligature = "C:\\Users\\\ufb01le.txt"
    assert accept_local_path(ligature) == ligature
    dotted = "C:\\Users\\.\\\ufb01le.txt"
    assert accept_local_path(dotted) == ligature
    assert accept_local_path("C:\\Users\\\uff0fx") is None


@pytest.mark.parametrize("kind", [0, 1, 4])
def test_blocked_drive_never_reaches_the_filesystem(kind, monkeypatch):
    import EasyTer
    from easyterpro import localpath

    localpath.clear_drive_type_cache()
    monkeypatch.setattr(localpath, "_query_drive_type", lambda _root: kind)
    calls = []
    monkeypatch.setattr(os.path, "isdir", lambda path: calls.append(("isdir", path)) or True)
    monkeypatch.setattr(os.path, "isfile", lambda path: calls.append(("isfile", path)) or True)
    monkeypatch.setattr(os.path, "exists", lambda path: calls.append(("exists", path)) or True)
    try:
        assert localpath.local_drive_ok(r"C:\proj\a.txt") is False
        assert EasyTer.existing_local_dir(r"C:\proj") is None
        assert EasyTer.existing_local_file(r"C:\proj\a.txt") is False
        assert calls == []
        assert localpath.hover_file_reference(r"C:\proj\a.txt") is False
    finally:
        localpath.clear_drive_type_cache()


def test_drive_type_is_cached_per_letter(monkeypatch):
    from easyterpro import localpath

    localpath.clear_drive_type_cache()
    calls = []

    def query(root):
        calls.append(root)
        return 3

    monkeypatch.setattr(localpath, "_query_drive_type", query)
    try:
        assert localpath.local_drive_ok(r"C:\a") is True
        assert localpath.local_drive_ok(r"c:\b") is True
        assert localpath.local_drive_ok(r"D:\a") is True
        assert calls == ["C:\\", "D:\\"]
        assert localpath.cached_drive_ok(r"C:\z") is True
        assert localpath.hover_file_reference(r"Z:\share\a.txt") is True
    finally:
        localpath.clear_drive_type_cache()


def test_hover_does_not_stat_or_probe_drives(monkeypatch):
    import EasyTer
    from easyterpro import localpath

    localpath.clear_drive_type_cache()

    def boom(*_args, **_kwargs):
        raise AssertionError("filesystem or drive probe")

    monkeypatch.setattr(os.path, "isfile", boom)
    monkeypatch.setattr(os.path, "isdir", boom)
    monkeypatch.setattr(os, "stat", boom)
    monkeypatch.setattr(localpath, "_query_drive_type", boom)
    try:
        assert localpath.hover_file_reference(r"C:\proj\src\app.py") is True
        widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
        widget.sel_anchor = None
        widget._url_at = lambda _pos: None
        widget._file_at = boom
        widget._file_candidate = lambda _pos: (r"C:\proj\src\app.py", 12)
        widget.setCursor = lambda *_a, **_k: None
        widget.unsetCursor = lambda: None

        class _Event:
            def buttons(self):
                return EasyTer.Qt.NoButton

            def modifiers(self):
                return EasyTer.Qt.ControlModifier

            def position(self):
                return None

        widget.mouseMoveEvent(_Event())
    finally:
        localpath.clear_drive_type_cache()


def test_click_relative_slashes_and_home(monkeypatch):
    import EasyTer

    def expanduser(path):
        if path == "~":
            return r"C:\Users\me"
        return path

    monkeypatch.setattr(os.path, "expanduser", expanduser)
    assert EasyTer.resolve_click_path("src/app.py", r"C:\proj") == r"C:\proj\src\app.py"
    assert EasyTer.resolve_click_path("src/app.py:12", r"C:\proj") == r"C:\proj\src\app.py"
    assert EasyTer.resolve_click_path("src/app.py:12:3", r"C:\proj") == r"C:\proj\src\app.py"
    assert EasyTer.resolve_click_path("~/x.py", r"C:\elsewhere") == r"C:\Users\me\x.py"
    assert EasyTer.resolve_click_path("~/dir/x.py:4", r"C:\elsewhere") == r"C:\Users\me\dir\x.py"
    assert EasyTer.resolve_click_path("C:/src/app.py", r"C:\proj") == r"C:\src\app.py"
    assert EasyTer.resolve_click_path(r"C:\src/app.py", r"C:\proj") is None
    assert EasyTer.resolve_click_path("//evil/share/a.py", r"C:\proj") is None


def test_osc6969_confirm_does_not_stack(monkeypatch):
    import EasyTer

    widget = EasyTer.TerminalWidget.__new__(EasyTer.TerminalWidget)
    widget._session = lambda: None
    shown = []

    def confirm(_parent, path):
        shown.append(path)
        widget._on_edit_file(r"C:\b\two.txt")
        return False

    monkeypatch.setattr(EasyTer, "confirm_local_open", confirm)
    monkeypatch.setattr(EasyTer, "EDIT_CONFIRM_INTERVAL", 60.0)
    widget._on_edit_file(r"C:\a\one.txt")
    widget._on_edit_file(r"C:\c\three.txt")
    assert shown == [r"C:\a\one.txt"]
    widget._edit_confirm_not_before = 0.0
    widget._on_edit_file(r"C:\d\four.txt")
    assert shown == [r"C:\a\one.txt", r"C:\d\four.txt"]


def test_load_file_skips_a_remote_drive(qapp, monkeypatch):
    import EasyTer
    from easyterpro import localpath

    localpath.clear_drive_type_cache()
    monkeypatch.setattr(localpath, "_query_drive_type", lambda _root: 4)
    calls = install_guard(monkeypatch)
    editor = EasyTer.EditorWidget()
    try:
        editor.load_file(r"C:\Users\x\a.txt")
        assert editor.path is None
        assert calls == []
    finally:
        localpath.clear_drive_type_cache()


def test_open_dialog_does_not_gate_a_user_path(qapp, monkeypatch):
    import EasyTer
    from io import StringIO

    unc = r"\\files\share\note.txt"
    assert accept_local_path(unc) is None
    monkeypatch.setattr(EasyTer.QFileDialog, "getOpenFileName", lambda *_a, **_k: (unc, ""))
    monkeypatch.setattr(EasyTer, "accept_local_path", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("gate")))
    monkeypatch.setattr(EasyTer, "local_drive_ok", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("drive")))
    monkeypatch.setattr("builtins.open", lambda file, *_a, **_k: StringIO("from-share"))
    editor = EasyTer.EditorWidget()
    editor.open_dialog()
    assert editor.path == unc
    assert editor._user_chosen is True
    assert editor.edit.toPlainText() == "from-share"


def test_save_as_does_not_gate_a_user_path(qapp, monkeypatch):
    import tempfile

    import EasyTer

    unc = r"\\files\share\note.txt"
    assert accept_local_path(unc) is None
    monkeypatch.setattr(EasyTer.QFileDialog, "getSaveFileName", lambda *_a, **_k: (unc, ""))
    monkeypatch.setattr(EasyTer, "accept_local_path", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("gate")))
    monkeypatch.setattr(EasyTer, "local_drive_ok", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("drive")))
    saved = {}

    def mkstemp(**kwargs):
        saved["dir"] = kwargs.get("dir")
        return 7, unc + ".tmp"

    class _Handle:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def write(self, text):
            saved["text"] = text

    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(os, "fdopen", lambda *_a, **_k: _Handle())
    monkeypatch.setattr(os, "replace", lambda _src, dst: saved.__setitem__("dst", dst))
    editor = EasyTer.EditorWidget()
    editor.edit.setPlainText("body")
    editor.save_as()
    assert editor.path == unc
    assert editor._user_chosen is True
    assert saved["dst"] == unc
    assert saved["text"] == "body"
    assert saved["dir"] == ntpath.dirname(unc)
    assert saved["dir"].startswith("\\\\")


def test_gated_save_keeps_the_arabic_error(qapp):
    import EasyTer
    import i18n

    i18n.set_language("ar")
    try:
        editor = EasyTer.EditorWidget()
        editor.path = r"\\evil\share\secret.txt"
        editor._user_chosen = False
        editor.edit.setPlainText("nope")
        editor.save()
        assert editor.path is None
        assert editor.header.text() == i18n.t("editor.save_rejected")
        assert "قرص محلي" in editor.header.text()
        assert editor.header.text() != "  ✎ " + i18n.t("editor.untitled")
    finally:
        i18n.set_language("en")
