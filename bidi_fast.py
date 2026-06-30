"""Hot character/BiDi helpers, extracted so they can be optionally compiled.

These pure-Python functions are the per-character work EasyTer does on every
line in Claude mode (visual->logical reordering, Arabic run detection, cluster
reversal). They are pure (str in, str/bool out) and called in tight loops, so
they are good candidates for native acceleration.

Acceleration model (single source, no fork):
    cythonize this file -> bidi_fast.cp3XX-win_amd64.pyd  shadows this .py,
    so `import bidi_fast` is fast when the extension is built and falls back to
    this pure-Python version when it is not. Build is OPTIONAL.

Output is identical to the in-line originals in EasyTer.py (verified by test).
"""
import unicodedata

_LTR_PUNCT = "._-/:\\@~+=#&%"


def _is_ltr_char(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    return (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A) or \
           (0x30 <= o <= 0x39) or (0xC0 <= o <= 0x2AF) or \
           (0x0660 <= o <= 0x0669) or (0x06F0 <= o <= 0x06F9)  # Arabic-Indic / Persian digits


def _is_inner_ltr(ch):
    # characters that stay inside an LTR island (paths, file names, version numbers...)
    return ch in "._-/:\\@~+=#&%" or _is_ltr_char(ch)


def _is_arabic_letter(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    # Arabic-Indic / Persian digits are numbers, not letters: like 0-9 they form a
    # weak LTR run and must keep their digit order (so ١٧٥ doesn't flip to ٥٧١).
    if (0x0660 <= o <= 0x0669) or (0x06F0 <= o <= 0x06F9):
        return False
    return (0x0600 <= o <= 0x06FF) or (0x0750 <= o <= 0x077F) or \
           (0xFB50 <= o <= 0xFDFF) or (0xFE70 <= o <= 0xFEFF)


def _arabic_after_spaces(cells, k, n):
    while k < n and cells[k][1] == " ":
        k += 1
    return k < n and _is_arabic_letter(cells[k][1])


def _rev_clusters(s):
    """Reverse character order while keeping each base character together with
    its following combining marks (Arabic diacritics)."""
    units = []
    for ch in s:
        if units and unicodedata.combining(ch):
            units[-1] += ch
        else:
            units.append(ch)
    units.reverse()
    return "".join(units)


def line_is_rtl_visual(text):
    ar = lt = 0
    for ch in text:
        if _is_arabic_letter(ch):
            ar += 1
        elif _is_ltr_char(ch) and ch.isalpha():
            lt += 1
    return ar > 0 and ar >= lt


def unbidi_rtl_line(line):
    rev = _rev_clusters(line)
    out = []
    i, n = 0, len(rev)
    while i < n:
        if _is_ltr_char(rev[i]):
            j = i
            while j < n:
                cj = rev[j]
                if _is_ltr_char(cj):
                    j += 1
                elif cj in _LTR_PUNCT and j + 1 < n and _is_ltr_char(rev[j + 1]):
                    j += 1
                elif cj == " " and j + 1 < n and _is_ltr_char(rev[j + 1]):
                    j += 1
                else:
                    break
            out.append(_rev_clusters(rev[i:j]))
            i = j
        else:
            out.append(rev[i])
            i += 1
    return "".join(out)


def _has_arabic(text):
    return any(_is_arabic_letter(c) for c in text)


def reverse_arabic_runs(line):
    out = []
    i, n = 0, len(line)
    while i < n:
        if _is_arabic_letter(line[i]):
            j = i
            while j < n and (_is_arabic_letter(line[j]) or
                             (line[j] == ' ' and j + 1 < n and _is_arabic_letter(line[j + 1]))):
                j += 1
            out.append(_rev_clusters(line[i:j]))
            i = j
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def restore_bidi_line(text):
    """Convert a Claude visual line to logical, by base direction. None = no change."""
    if line_is_rtl_visual(text):
        return unbidi_rtl_line(text)
    if _has_arabic(text):
        return reverse_arabic_runs(text)
    return None
