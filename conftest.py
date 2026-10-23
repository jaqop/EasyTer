"""Repo-root pytest hooks. Loaded for tests/ and dev/ alike."""

import os

# Headless Qt. Set before PySide6 chooses a platform plugin (CI has no display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
