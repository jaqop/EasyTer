"""Regression test for cmd_is_claude() - the Arabic-in-git-diff bug.

Bug: EasyTer auto-enabled Claude mode on ANY entry into the alternate screen
(\\x1b[?1049h). The grid engine reverses every Arabic run because Claude
pre-reverses Arabic on Windows - but pagers/editors (git's less, vim, man,
htop, ...) also use the alternate screen while emitting LOGICAL-order Arabic,
so reversing them shredded the text (fragmented words, gaps, mis-placed
highlight blocks in `git diff`).

Fix: auto Claude-mode is now gated on the INVOKED PROGRAM actually being
Claude, via cmd_is_claude(running_cmd). This test pins that behaviour so the
pager case can never silently regress.

Run:  python -m unittest test_claude_detection
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (parent of dev/)

try:
    from EasyTer import cmd_is_claude
except Exception as e:        # PySide6/pywinpty missing in this env - skip, don't fail
    cmd_is_claude = None
    _import_error = e


@unittest.skipIf(cmd_is_claude is None, "EasyTer import failed (GUI deps missing)")
class CmdIsClaudeTest(unittest.TestCase):
    def test_claude_invocations_match(self):
        for cmd in [
            "claude",
            "claude --help",
            "claude.cmd",
            r"C:\tools\claude.exe",
            'C:\\Users\\Admin\\AppData\\claude.exe --dangerously',
            "npx claude",
            "uvx claude",
            '& "C:\\x\\claude.exe"',
        ]:
            self.assertTrue(cmd_is_claude(cmd), f"expected Claude: {cmd!r}")

    def test_pagers_and_editors_do_not_match(self):
        # THE REGRESSION: these enter the alternate screen but are NOT Claude.
        for cmd in [
            "git diff",
            "git diff --no-index a.txt b.txt",
            "git log claude",          # 'claude' is a file/branch arg, not the program
            "git show",
            "vim claude.py",           # editing a file named claude
            "less claude.txt",
            "nano claude.md",
            "man less",
            "htop",
            "bat README.ar.md",
        ]:
            self.assertFalse(cmd_is_claude(cmd), f"must NOT be Claude: {cmd!r}")

    def test_idle_prompt_is_not_claude(self):
        for cmd in ["", "   ", None]:
            self.assertFalse(cmd_is_claude(cmd), f"must NOT be Claude: {cmd!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
