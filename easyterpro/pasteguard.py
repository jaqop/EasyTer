# -*- coding: utf-8 -*-
"""Shared paste guard for EasyTer and EasyTer Pro.

A paste is confirmed when it is multi-line, oversized, or contains a control
character other than tab. Bracketed-paste wrapping is applied after the
confirm, and an embedded paste-end marker is stripped so the pasted text
cannot close the bracket and run the rest.
"""

from typing import Callable, Optional

# Same threshold the EasyTer dialog has always used for a "large" paste.
PASTE_LARGE = 2000


def paste_needs_warning(text) -> bool:
    """True for multi-line, oversized, or control-character pastes.

    Tab is ordinary indentation. Newline, carriage return, escape, and the
    other C0 controls can submit or inject input, so they warn even when the
    paste is a single short line.
    """
    if not isinstance(text, str) or text == "":
        return False
    if len(text) > PASTE_LARGE:
        return True
    if "\n" in text or "\r" in text:
        return True
    for ch in text:
        code = ord(ch)
        if code == 127 or (code < 32 and ch != "\t"):
            return True
    return False


def bracket_paste(text: str, bracketed: bool) -> str:
    """Normalize newlines and wrap when the program enabled bracketed paste.

    Every ESC and U+009B is removed first. A single pass over ``\\x1b[201~``
    leaves a real end marker when the marker itself contains an escape
    (``\\x1b[20\\x1b[201~1~``). Kitty and WezTerm drop these bytes from a paste
    so the pasted text cannot close the bracket.
    """
    body = text.replace("\r\n", "\r").replace("\n", "\r")
    body = body.replace("\x1b", "").replace("\x9b", "")
    if not bracketed:
        return body
    return "\x1b[200~" + body + "\x1b[201~"


def guarded_paste(text, *, bracketed, protection, confirm: Callable[[str], bool]) -> Optional[str]:
    """Text to write to the shell, or None when the paste is empty or refused.

    ``confirm`` is called only when ``protection`` is on and the paste needs a
    warning. It must be a UI-thread dialog; this function does not import Qt.
    """
    if not isinstance(text, str) or text == "":
        return None
    if protection and paste_needs_warning(text):
        if not confirm(text):
            return None
    return bracket_paste(text, bool(bracketed))
