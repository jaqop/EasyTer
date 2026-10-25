# -*- coding: utf-8 -*-
"""Quote a path for a known shell, and decide what a drop may write.

``accept_local_path`` is not a quoter. It accepts ``'``, ``;``, ``&``, ``$(``
and backticks, all of which are shell syntax. A drop is also not required to
be a local path.

``quote_shell_path`` is for a command that is known to be PowerShell, cmd, or
POSIX (the oh-my-posh lines, and a file drop the user has confirmed). A path
with no shell metacharacter is double-quoted without asking. A metacharacter,
or a trailing backslash, is quoted for the pane's shell and shown first.
"""

import ntpath
import re
import unicodedata
from typing import Optional

# PowerShell treats these as single quotes, not only U+0027.
_PS_SINGLE_QUOTES = re.compile("['\u2018\u2019\u201a\u201b]")

# Metacharacters of PowerShell, cmd, or POSIX. A path that contains one is not
# auto-inserted. Backslash is not in this set: inside double quotes it is
# literal in all three shells, and every Windows path contains one.
# Double-quote lookalikes are included because PowerShell accepts them as `"`.
_SHELL_SPECIAL = frozenset(
    "$'\"%!^&|<>;()`"
    "\u2018\u2019\u201a\u201b"
    "\u201c\u201d\u201e\u201f"
)

_FAMILIES = ("powershell", "cmd", "posix")

# Longer names first so ``pwsh.exe`` is not classified by the ``pwsh`` prefix
# check below; matching is on the executable leaf, not a substring.
_EXE_FAMILY = (
    ("powershell.exe", "powershell"),
    ("pwsh.exe", "powershell"),
    ("powershell", "powershell"),
    ("pwsh", "powershell"),
    ("cmd.exe", "cmd"),
    ("cmd", "cmd"),
    ("bash.exe", "posix"),
    ("wsl.exe", "posix"),
    ("zsh.exe", "posix"),
    ("sh.exe", "posix"),
    ("bash", "posix"),
    ("wsl", "posix"),
    ("zsh", "posix"),
    ("sh", "posix"),
)


def shell_family(command) -> Optional[str]:
    """``powershell``, ``cmd``, or ``posix`` for a pane command, else None."""
    if isinstance(command, (list, tuple)):
        command = command[0] if command else ""
    if not isinstance(command, str):
        return None
    leaf = ntpath.basename(_executable(command)).lower()
    for name, family in _EXE_FAMILY:
        if leaf == name:
            return family
    return None


def _has_control(text: str) -> bool:
    """True when ``text`` contains a Unicode Cc character (C0, DEL, or C1)."""
    return any(unicodedata.category(ch) == "Cc" for ch in text)


def quote_shell_path(path, shell="powershell") -> Optional[str]:
    """A quoted path for ``shell``, or None when it cannot be quoted safely.

    Any Cc character is refused. Stripping it would change the name, and
    writing it lets the shell read a keystroke. cmd refuses a path that
    contains ``"`` or ``%`` (neither is neutralized by double quotes) and a
    path ending in ``^`` (that caret escapes the closing quote). ``!`` is
    written as ``^!`` because delayed expansion still sees it inside quotes.
    ``^ & | < >`` are literal inside cmd double quotes, so they are not
    caret-escaped: a caret would become part of the filename.

    PowerShell single quotes double U+0027 and U+2018..U+201B. PowerShell
    treats all five as quotes.
    """
    if not isinstance(path, str) or path == "":
        return None
    if _has_control(path):
        return None
    if shell in _FAMILIES:
        family = shell
    else:
        family = shell_family(shell)
    if family == "powershell":
        quoted = "'" + _PS_SINGLE_QUOTES.sub(lambda m: m.group(0) * 2, path) + "'"
    elif family == "cmd":
        quoted = _quote_cmd(path)
    elif family == "posix":
        quoted = "'" + path.replace("'", "'\\''") + "'"
    else:
        quoted = None
    if not quoted or _has_control(quoted):
        return None
    return quoted


def _drop_needs_confirm(path: str) -> bool:
    """True for a shell metacharacter or a trailing backslash.

    ``"C:\\"`` is special to CommandLineToArgvW: the backslash escapes the
    closing quote. A backslash anywhere else is a path separator.
    """
    if path.endswith("\\"):
        return True
    return any(ch in _SHELL_SPECIAL for ch in path)


def prepare_dropped_files(parts, shell) -> Optional[tuple]:
    """``(text, needs_confirm)`` for dropped file paths, or None to refuse.

    A Cc character refuses the whole drop. A path with no metacharacter and
    no trailing backslash is wrapped in double quotes and does not ask.
    Anything else is quoted for ``shell`` and ``needs_confirm`` is True. The
    text is that quoted form, never the raw path. A part ``shell`` cannot
    quote refuses the whole drop.
    """
    if not parts:
        return None
    cleaned = []
    confirm = False
    for part in parts:
        if not isinstance(part, str) or part == "":
            return None
        if _has_control(part):
            return None
        if _drop_needs_confirm(part):
            confirm = True
        cleaned.append(part)
    if not confirm:
        return " ".join('"' + part + '"' for part in cleaned), False
    quoted_parts = []
    for part in cleaned:
        quoted = quote_shell_path(part, shell)
        if not quoted:
            return None
        quoted_parts.append(quoted)
    return " ".join(quoted_parts), True


def sanitize_dropped_text(text) -> Optional[str]:
    """Dropped text made safe to write, or None if nothing remains.

    Newlines become a single space so a multi-line drop stays one line
    (``a\\nb`` is ``a b``). Every other Cc character is removed, including
    C1 (U+0080–U+009F) and DEL (U+007F), not only C0. Those are keystrokes
    even inside quotes.
    """
    if not isinstance(text, str) or text == "":
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = []
    for ch in text:
        if ch == "\n":
            cleaned.append(" ")
        elif unicodedata.category(ch) == "Cc":
            continue
        else:
            cleaned.append(ch)
    result = "".join(cleaned)
    if result == "":
        return None
    return result


def reveal_format_chars(text) -> str:
    """Replace Cf, Zl and Zp characters with ``<U+XXXX>`` for a confirm card.

    Bidi and other format characters would otherwise reorder the path the
    user is asked to approve. U+2028 and U+2029 are Zl/Zp rather than Cf, and
    Qt lays both out as real line breaks even under ``Qt.PlainText``, so they
    can split the path and leave room for forged dialog copy beneath it.
    The bytes written to the shell are unchanged.
    """
    if not isinstance(text, str):
        return ""
    return "".join(
        "<U+%04X>" % ord(ch) if unicodedata.category(ch) in ("Cf", "Zl", "Zp") else ch
        for ch in text
    )


def quote_dropped_text(parts, shell) -> Optional[str]:
    """Join dropped chunks for ``shell``, or None if any chunk is unsafe.

    One refused path refuses the whole drop, so a safe file cannot be used
    to smuggle an unquotable neighbor.
    """
    if not parts:
        return None
    chunks = []
    for part in parts:
        quoted = quote_shell_path(part, shell)
        if not quoted:
            return None
        chunks.append(quoted)
    return " ".join(chunks)


def _quote_cmd(path: str) -> Optional[str]:
    if '"' in path or "%" in path or path.endswith("^"):
        return None
    return '"' + path.replace("!", "^!") + '"'


def _executable(command: str) -> str:
    """The executable token, keeping spaces that belong to its path."""
    text = command.strip()
    if not text:
        return ""
    if text[0] == '"':
        end = text.find('"', 1)
        return text[1:end] if end > 1 else text.strip('"')
    lower = text.lower()
    for name, _family in _EXE_FAMILY:
        start = 0
        while True:
            idx = lower.find(name, start)
            if idx < 0:
                break
            end = idx + len(name)
            before_ok = idx == 0 or text[idx - 1] in "\\/:"
            after_ok = end == len(text) or text[end] in " \t\""
            if before_ok and after_ok:
                return text[:end].strip('"')
            start = idx + 1
    return text.split()[0]
