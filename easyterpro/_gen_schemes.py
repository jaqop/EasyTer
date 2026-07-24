# -*- coding: utf-8 -*-
"""أداة بناء: تحوّل ثيمات iTerm2-Color-Schemes (صيغة Windows Terminal) إلى
`schemes.json` بصيغة easyterpro. تُشغَّل مرّةً بعد استنساخ المجموعة:

    git clone --depth 1 https://github.com/mbadolato/iTerm2-Color-Schemes <dir>
    python easyterpro/_gen_schemes.py <dir>/windowsterminal
"""
import json
import os
import glob
import sys

# Windows Terminal يسمّي magenta بـ"purple" → نعيد التسمية لصيغة pyte/easyterpro
_MAP = {
    "black": "black", "red": "red", "green": "green", "yellow": "yellow",
    "blue": "blue", "purple": "magenta", "cyan": "cyan", "white": "white",
    "brightBlack": "brightblack", "brightRed": "brightred", "brightGreen": "brightgreen",
    "brightYellow": "brightyellow", "brightBlue": "brightblue", "brightPurple": "brightmagenta",
    "brightCyan": "brightcyan", "brightWhite": "brightwhite",
}


def main(src):
    out = {}
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
            name = (j.get("name") or os.path.splitext(os.path.basename(f))[0]).strip()
            ansi = {dst: j[wt] for wt, dst in _MAP.items()}
            out[name] = {"bg": j["background"], "fg": j["foreground"], "ansi": ansi}
        except (KeyError, ValueError):
            continue
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemes.json")
    with open(dst, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False)
    print("wrote", len(out), "schemes ->", dst)


if __name__ == "__main__":
    default = os.path.join(os.environ.get("TEMP", "."), "iterm_schemes", "windowsterminal")
    main(sys.argv[1] if len(sys.argv) > 1 else default)
