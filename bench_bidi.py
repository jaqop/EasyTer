"""Correctness + timing harness for bidi_fast (pure vs compiled).

- Verifies bidi_fast.* produces identical output to EasyTer's in-line originals.
- Times restore_bidi_line over a realistic Arabic corpus.

Run before building:  python bench_bidi.py        (pure Python)
Build the extension :  python setup_accel.py build_ext --inplace
Run after building  :  python bench_bidi.py        (now uses the .pyd, shadows .py)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bidi_fast

# detect whether we imported the compiled extension or the .py
compiled = bidi_fast.__file__.endswith((".pyd", ".so"))
print(f"bidi_fast loaded from: {os.path.basename(bidi_fast.__file__)}  "
      f"({'COMPILED' if compiled else 'pure python'})\n")

# realistic corpus: RTL-dominant Arabic, Arabic-with-Latin-islands, mixed
samples = [
    "الواعظُ الشابُّ آليّه ف9، أيطلُبُ لنفسه شيئاً؟ لا مالاً ولا منصباً يا سيّدي.",
    "والذين يأتونَ ليسمَعوا الضربتَين B4، أم ليَروا رجلاً يُحبُّهم ف015؟",
    "ثوران تركَ المجلسَ في الكهنةِ يطول. بالثيرا رفعَ نصفَ ثانيةٍ config.txt هنا.",
    "What are you working on ؟مويلا لمعت اذام لوح ثدحتن انعد",
    "diff --git a/الفصل.md b/الفصل.md  C:\\Users\\Admin\\رواية\\ف015.md",
]
N = 5000
lines = [samples[i % len(samples)] for i in range(N)]

# --- correctness vs the originals in EasyTer.py ---
import EasyTer
mismatch = 0
for s in lines[:len(samples)*3] + samples:
    if bidi_fast.restore_bidi_line(s) != EasyTer.restore_bidi_line(s):
        mismatch += 1
    if bidi_fast.unbidi_rtl_line(s) != EasyTer.unbidi_rtl_line(s):
        mismatch += 1
    if bidi_fast.reverse_arabic_runs(s) != EasyTer.reverse_arabic_runs(s):
        mismatch += 1
print(f"correctness vs EasyTer originals: {'OK (identical)' if mismatch == 0 else f'{mismatch} MISMATCHES'}")

def timeit(fn, reps=3):
    best = min(_one(fn) for _ in range(reps))
    return best
def _one(fn):
    t0 = time.perf_counter(); fn(); return time.perf_counter() - t0

t = timeit(lambda: [bidi_fast.restore_bidi_line(s) for s in lines])
print(f"restore_bidi_line : {t*1000:7.2f} ms / {N} lines  | {t/N*1e6:6.2f} us/line")

allchars = "".join(lines)
t = timeit(lambda: [bidi_fast._is_arabic_letter(c) for c in allchars])
print(f"_is_arabic_letter : {t*1000:7.2f} ms / {len(allchars)} chars | {t/len(allchars)*1e9:5.1f} ns/char")

t = timeit(lambda: [bidi_fast._rev_clusters(s) for s in lines])
print(f"_rev_clusters     : {t*1000:7.2f} ms / {N} lines  | {t/N*1e6:6.2f} us/line")
