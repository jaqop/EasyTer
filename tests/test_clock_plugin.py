# -*- coding: utf-8 -*-
"""Tests for the corner-clock plugin's pure time formatter (no Qt)."""

import datetime

from easyterpro.plugins import clock_corner as plug


def test_format_time_24h_hms():
    assert plug.format_time(datetime.datetime(2020, 1, 1, 13, 5, 9)) == "13:05:09"


def test_format_time_midnight():
    assert plug.format_time(datetime.datetime(2020, 1, 1, 0, 0, 0)) == "00:00:00"


def test_format_time_zero_pads():
    assert plug.format_time(datetime.datetime(2020, 1, 1, 9, 8, 7)) == "09:08:07"
