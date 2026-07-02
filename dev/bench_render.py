"""Render-path micro-benchmark: why _draw_run coalesces FormatRanges.

EasyTer shapes each grid run with a single QTextLayout and colours the cells
with QTextLayout.FormatRange. The number of FormatRanges dominates the per-line
cost: building one range PER CELL (as a colourful `git diff` line would need) is
~6-7x slower than coalescing adjacent same-style cells into a few ranges. The
output is the same connected, correctly-coloured Arabic (Qt itemises Arabic at
format boundaries, so fewer ranges = fewer shaping breaks, i.e. equal-or-better
joining). This benchmark pins those numbers so the coalescing in _draw_run is
not "simplified" away by a future change.

Run:  python bench_render.py        (uses the offscreen Qt platform)
"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import (QFont, QTextLayout, QTextOption, QTextCharFormat,
                               QColor, QPainter, QImage)
    from PySide6.QtCore import Qt, QPointF
except Exception as e:                       # GUI deps missing - nothing to do
    print("PySide6 not available, skipping benchmark:", e)
    sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (parent of dev/)
app = QApplication(sys.argv)
import EasyTer
EasyTer._ensure_arabic_font()

font = QFont()
font.setFamilies(["JetBrains Mono", "Cascadia Mono", "Consolas", "Vazirmatn", "Amiri"])
font.setStyleHint(QFont.Monospace)
font.setPointSize(13)
font.setHintingPreference(QFont.PreferFullHinting)

base = ("الواعظُ الشابُّ آليّه ف{0}، أيطلُبُ لنفسه شيئاً؟ لا مالاً ولا منصباً يا سيّدي. "
        "والذين يأتونَ ليسمَعوا الضربتَين B{0}، أم ليَروا رجلاً يُحبُّهم ف{0}؟")
N = 2000
lines = [base.format(i) for i in range(N)]   # all unique = every line is a cache miss

img = QImage(2400, 48, QImage.Format_ARGB32_Premultiplied)
painter = QPainter(img)
painter.setFont(font)

def build(text, nranges):
    layout = QTextLayout(text, font)
    opt = QTextOption(); opt.setWrapMode(QTextOption.NoWrap)
    opt.setTextDirection(Qt.RightToLeft)
    layout.setTextOption(opt)
    frs = []
    n = len(text); step = max(1, n // nranges); pos = 0
    while pos < n:
        f = QTextCharFormat(); f.setForeground(QColor("#cccccc"))
        fr = QTextLayout.FormatRange(); fr.start = pos; fr.length = min(step, n - pos); fr.format = f
        frs.append(fr); pos += step
    layout.setFormats(frs)
    layout.beginLayout()
    ln = layout.createLine(); ln.setLineWidth(100000); ln.setPosition(QPointF(0, 0))
    layout.endLayout()
    _ = ln.naturalTextWidth()

def run(nranges):
    t0 = time.perf_counter()
    for s in lines:
        build(s, nranges if nranges else len(s))
    return (time.perf_counter() - t0) / N * 1e6   # us/line

print(f"{N} unique Arabic lines, avg {sum(map(len, lines))//N} chars\n")
percell = run(0)
print(f"FormatRange per cell  (old)     : {percell:6.1f} us/line")
for ns in (10, 5, 3, 1):
    us = run(ns)
    print(f"coalesced to {ns:2d} range(s)         : {us:6.1f} us/line   ({percell/us:.1f}x faster)")
painter.end()
