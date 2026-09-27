"""Tests of the logging helpers."""

from __future__ import annotations

import logging

from cantcp.logger import TRACE


def test_trace_level() -> None:
    assert TRACE == 5
    assert TRACE < logging.DEBUG < logging.INFO < logging.WARNING


def test_level_name_registered() -> None:
    assert logging.getLevelName(TRACE) == "TRACE"
    assert logging.getLevelName("TRACE") == TRACE
