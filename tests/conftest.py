# -*- coding: utf-8 -*-
"""Shared test fixtures for the EasyTer Pro test suite."""

import os

import pytest

from easyterpro import pluginhost

# Headless Qt (CI and local). Must be set before PySide6 loads a platform plugin.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _redirect_plugin_log(tmp_path, monkeypatch):
    """Keep plugin-host logging out of the user's real ~/.easyterpro/plugins.log.

    Several tests deliberately trigger import/register/hook failures, which the
    host logs. Redirect that log to pytest's tmp dir so test runs never pollute
    the live runtime log."""
    monkeypatch.setattr(pluginhost, "_LOG_PATH", str(tmp_path / "plugins.log"))
