# -*- coding: utf-8 -*-
"""Quote a path for a known shell, and decide what a drop may write.

``accept_local_path`` is not a quoter. It accepts ``'``, ``;``, ``&``, ``$(``
and backticks, all of which are shell syntax. A drop is also not required to
be a local path.

``quote_shell_path`` is for a command that is known to be PowerShell, cmd, or
POSIX (the oh-my-posh lines). The pane's tab command is not that knowledge:
the user may have started cmd inside pwsh, or ssh. File drops therefore use
``prepare_dropped_files``, which double-quotes only a path with no shell
metacharacter and otherwise asks the UI to confirm the literal text.
"""

import ntpath
import re
import unicodedata
from typing import Optional

# PowerShell treats these as single quotes, not only U+0027.
_PS_SINGLE_QUOTES = re.compile("['\u2018\u2019\u201a\u201b]")

# Metacharacters of PowerShell, cmd, or POSIX. A path that contains one is not
# auto-inserted: the tab's shell may not be the program that will read it.
# Double-quote lookalikes are included because PowerShell accepts them as `"`.
_SHELL_SPECIAL = frozenset(
    "$\\'\"%!^&|<>;()`"
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


def prepare_dropped_files(parts) -> Optional[tuple]:
    """``(text, needs_confirm)`` for dropped file paths, or None to refuse.

    A Cc character refuses the whole drop. A shell metacharacter returns the
    paths joined literally and ``needs_confirm`` True: the UI shows that exact
    text and writes it only after the user accepts. Anything else is wrapped
    in double quotes, which is safe in PowerShell, cmd, and POSIX when the
    path has none of those characters. The tab's shell is not consulted.
    """
    if not parts:
        return None
    literals = []
    special = False
    for part in parts:
        if not isinstance(part, str) or part == "":
            return None
        if _has_control(part):
            return None
        if any(ch in _SHELL_SPECIAL for ch in part):
            special = True
        literals.append(part)
    if special:
        return " ".join(literals), True
    return " ".join('"' + part + '"' for part in literals), False


def sanitize_dropped_text(text) -> Optional[str]:
    """Dropped text with every Cc character removed, or None if nothing remains.

    Text is not a path and is not quoted. Cc characters are keystrokes (Ctrl+U
    clears the line, Ctrl+O accepts it) even inside quotes.
    """
    if not isinstance(text, str) or text == "":
        return None
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    if cleaned == "":
        return None
    return cleaned


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
