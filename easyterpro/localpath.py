# -*- coding: utf-8 -*-
"""Lexical gate for paths that came from the terminal.

Windows authenticates to a remote host when a process touches a UNC path, and
that handshake sends the user's NTLM credentials. Terminal output is untrusted,
so a path from an OSC report (or derived from one) must never reach isdir,
stat, open, startfile, or a child process until it has passed through
``accept_local_path``.

``accept_local_path`` is purely lexical. It does not call the filesystem: on
Windows those calls are exactly the leak. ``local_drive_ok`` is a separate
check, used after the gate and before a filesystem call, that rejects drive
letters ``GetDriveTypeW`` reports as remote, missing, or unknown.
"""

import sys
import ntpath
import unicodedata
import urllib.parse
from typing import Optional

# DOS device names. Windows treats NAME, NAME.ext, and trailing dots/spaces as
# the device, so the stem is compared, not the whole component. COM0/LPT0 are
# reserved on current Windows the same way COM1 and LPT1 are.
_DOS_DEVICES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$", "COM0", "LPT0"]
    + [f"COM{n}" for n in range(1, 10)]
    + [f"LPT{n}" for n in range(1, 10)]
)

# GetDriveTypeW values that must not be touched. REMOTE is a mapped share
# (authenticates). NO_ROOT_DIR and UNKNOWN cover a missing or disconnected
# letter, which can block the calling thread while Windows retries it.
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
_BLOCKED_DRIVE_TYPES = frozenset({DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOTE})
_DRIVE_CACHE = {}

# Bidi controls can hide a UNC prefix from the confirmation dialog and from a
# reader skimming the path. Reject them rather than trying to display them.
_BIDI_CONTROLS = frozenset(
    [0x061C, 0x200E, 0x200F]
    + list(range(0x202A, 0x2030))
    + list(range(0x2066, 0x2070))
)


def osc7_host_ok(host) -> bool:
    """OSC 7 may name a local file only when the URI host is empty or localhost.

    ``file://other-host/...`` is a different machine. Some Windows APIs treat
    that URL as a WebDAV path and authenticate to it.
    """
    if not isinstance(host, str):
        return False
    return host.strip().casefold() in ("", "localhost")


def accept_local_path(p) -> Optional[str]:
    """Return a lexically normalized ``X:\\...`` path, or None.

    Percent-decoding and NFKC run as checks, so a separator hidden as ``%5C``,
    ``%2F``, or a fullwidth slash is visible to the same rules as a literal
    one. The decoded spelling and the compatibility spelling both have to
    survive. The returned string keeps the original characters: NFKC is not
    written back, so a name like ``ﬁle.txt`` is not rewritten to ``file.txt``.
    ``.`` and ``..`` are still collapsed with ``ntpath.normpath``.
    """
    if not isinstance(p, str) or _bad_chars(p):
        return None
    # strip() would hide a trailing newline or tab. Controls are rejected
    # above, so only ordinary whitespace is removed here.
    text = p.strip()
    if not text or _bad_chars(text):
        return None
    nfkc = unicodedata.normalize("NFKC", text)
    if _bad_chars(nfkc):
        return None
    decoded = _percent_decode(nfkc)
    if decoded is None:
        return None
    decoded = unicodedata.normalize("NFKC", decoded)
    if _bad_chars(decoded):
        return None
    if _canonical_drive_path(nfkc) is None or _canonical_drive_path(decoded) is None:
        return None
    return _canonical_drive_path(text)


def clear_drive_type_cache():
    """Drop cached ``GetDriveTypeW`` results. Tests use this between cases."""
    _DRIVE_CACHE.clear()


def cached_drive_ok(path):
    """True or False if this drive letter was already classified, else None.

    Does not call ``GetDriveTypeW``. Hover uses this so a disconnected
    network drive is never probed on mouse move.
    """
    letter = _drive_letter(path)
    if letter is None:
        return None
    return _DRIVE_CACHE.get(letter)


def local_drive_ok(path) -> bool:
    """False for ``DRIVE_REMOTE``, ``DRIVE_NO_ROOT_DIR``, and ``DRIVE_UNKNOWN``.

    The result is cached per drive letter. Call this only after
    ``accept_local_path``, and before ``isdir`` / ``isfile`` / ``open``.
    """
    letter = _drive_letter(path)
    if letter is None:
        return False
    cached = _DRIVE_CACHE.get(letter)
    if cached is not None:
        return cached
    try:
        kind = _query_drive_type(letter + ":\\")
    except OSError:
        return False
    ok = kind not in _BLOCKED_DRIVE_TYPES
    _DRIVE_CACHE[letter] = ok
    return ok


def hover_file_reference(path) -> bool:
    """Whether a resolved path may show the Ctrl+hover hand cursor.

    A drive already known to be remote, missing, or unknown is not hoverable.
    An uncached drive is: classifying it would call ``GetDriveTypeW`` on the
    UI thread. This function does not call the filesystem.
    """
    if cached_drive_ok(path) is False:
        return False
    return _drive_letter(path) is not None


def _drive_letter(path):
    if not isinstance(path, str) or len(path) < 3 or path[1] != ":":
        return None
    letter = path[0]
    if not letter.isascii() or not letter.isalpha():
        return None
    return letter.upper()


def _query_drive_type(root):
    """``GetDriveTypeW`` on Windows. Elsewhere every letter is a fixed drive.

    Non-Windows hosts have no mapped-drive probe, and the lexical gate is
    what the unit tests exercise there.
    """
    if sys.platform != "win32":
        return DRIVE_FIXED
    import ctypes
    return int(ctypes.windll.kernel32.GetDriveTypeW(root))


def _percent_decode(text: str) -> Optional[str]:
    """Decode ``%HH`` until stable. None if it is still changing after the cap."""
    cur = text
    for _ in range(8):
        if "%" not in cur:
            return cur
        try:
            nxt = urllib.parse.unquote(cur)
        except (ValueError, UnicodeError):
            return None
        if nxt == cur:
            return cur
        cur = nxt
    try:
        if urllib.parse.unquote(cur) != cur:
            return None
    except (ValueError, UnicodeError):
        return None
    return cur


def _canonical_drive_path(s: str) -> Optional[str]:
    """Normalize ``s`` lexically and require the result to still be a local drive.

    The pre-normalize string is checked too: ``normpath`` can walk ``..`` out of
    a device component or an ADS colon and leave a clean drive path behind.
    """
    if not _structurally_local(s):
        return None
    norm = ntpath.normpath(s)
    if not _structurally_local(norm) or not _is_drive_absolute(norm):
        return None
    return norm


def _structurally_local(s: str) -> bool:
    if _forbidden_prefix(s) or _mixed_separators(s) or _bad_chars(s):
        return False
    if _extra_colon(s) or _has_dos_device(s):
        return False
    return True


def _forbidden_prefix(s: str) -> bool:
    """UNC, device namespaces, NT object paths, and file: URLs."""
    if s[:5].lower() == "file:":
        return True
    folded = s.replace("/", "\\")
    if folded.startswith("\\\\"):
        return True
    if folded[:4].lower() == "\\??\\":
        return True
    return False


def _mixed_separators(s: str) -> bool:
    return "/" in s and "\\" in s


def _bad_chars(s: str) -> bool:
    if '"' in s or "," in s:
        return True
    for ch in s:
        if ord(ch) in _BIDI_CONTROLS:
            return True
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cs"):
            return True
    return False


def _extra_colon(s: str) -> bool:
    """A colon after the drive letter is an alternate data stream (``file:stream``)."""
    return ":" in s[2:]


def _is_dos_device(part: str) -> bool:
    name = part.rstrip(" .")
    if not name or name in (".", ".."):
        return False
    stem = name.split(".", 1)[0].rstrip(" .")
    return stem.upper() in _DOS_DEVICES


def _has_dos_device(s: str) -> bool:
    folded = s.replace("/", "\\")
    if len(folded) >= 2 and folded[1] == ":":
        folded = folded[2:]
    for part in folded.split("\\"):
        if _is_dos_device(part):
            return True
    return False


def _is_drive_absolute(s: str) -> bool:
    """True for ``C:\\`` and ``C:\\dir\\file`` only. ``C:rel`` and ``\\\\host`` are not."""
    if len(s) < 3 or s[1] != ":" or s[2] != "\\":
        return False
    letter = s[0]
    if not letter.isascii() or not letter.isalpha():
        return False
    drive, rest = ntpath.splitdrive(s)
    if drive != s[:2] or not rest.startswith("\\"):
        return False
    return ntpath.isabs(s)
