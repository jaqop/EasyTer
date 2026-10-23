# -*- coding: utf-8 -*-
"""Quote a dropped path for the shell that is actually running in the pane.

``accept_local_path`` is not a quoter. It accepts ``'``, ``;``, ``&``, ``$(``
and backticks, all of which are shell syntax. A drop is also not required to
be a local path: text and URLs can carry a carriage return, and a ``\\r``
written to the pane submits a command before the shell ever parses quotes.
Those characters are stripped here.

The family is taken from the pane's shell command (PowerShell, cmd, or
bash/WSL). An unrecognized shell is refused rather than guessed: cmd double
quotes are still expandable in PowerShell, and PowerShell single quotes are
not quotes in cmd.
"""

import ntpath
from typing import Optional

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


def quote_shell_path(path, shell="powershell") -> Optional[str]:
    """A quoted path for ``shell``, or None when it cannot be quoted safely.

    ``\\r`` and ``\\n`` are removed so the text cannot submit a line. cmd
    refuses a path that contains ``"`` or ``%`` (neither is neutralized by
    double quotes) and a path ending in ``^`` (that caret escapes the closing
    quote). ``!`` is written as ``^!`` because delayed expansion still sees it
    inside quotes. ``^ & | < >`` are literal inside cmd double quotes, so they
    are not caret-escaped: a caret would become part of the filename.
    """
    if not isinstance(path, str):
        return None
    cleaned = path.replace("\r", "").replace("\n", "")
    if cleaned == "":
        return None
    if shell in _FAMILIES:
        family = shell
    else:
        family = shell_family(shell)
    if family == "powershell":
        quoted = "'" + cleaned.replace("'", "''") + "'"
    elif family == "cmd":
        quoted = _quote_cmd(cleaned)
    elif family == "posix":
        quoted = "'" + cleaned.replace("'", "'\\''") + "'"
    else:
        quoted = None
    if not quoted or "\r" in quoted or "\n" in quoted:
        return None
    return quoted


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
