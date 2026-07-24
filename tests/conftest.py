# -*- coding: utf-8 -*-
"""Shared test fixtures for the EasyTer Pro test suite."""

import pytest

from easyterpro import pluginhost


@pytest.fixture(autouse=True)
def _redirect_plugin_log(tmp_path, monkeypatch):
    """Keep plugin-host logging out of the user's real ~/.easyterpro/plugins.log.

    Several tests deliberately trigger import/register/hook failures, which the
    host logs. Redirect that log to pytest's tmp dir so test runs never pollute
    the live runtime log."""
    monkeypatch.setattr(pluginhost, "_LOG_PATH", str(tmp_path / "plugins.log"))
