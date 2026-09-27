"""Tests of the Stats counters."""

from __future__ import annotations

from dataclasses import replace

from cantcp.stats import Stats


def test_defaults() -> None:
    stats = Stats()
    assert stats.skipped == 0
    assert stats.dropped == 0
    assert stats.bad_type == 0
    assert stats.bad_dlc == 0
    assert stats.bad_len == 0
    assert stats.truncated == 0


def test_equality_and_replace() -> None:
    stats = Stats(skipped=1, dropped=2, bad_type=3, bad_dlc=4, bad_len=5, truncated=6)
    copy = replace(stats)
    assert copy == stats
    assert copy is not stats
    other = replace(stats, skipped=0)
    assert other != stats
    assert other.skipped == 0
    assert stats.skipped == 1


def test_keyword_construction() -> None:
    stats = Stats(skipped=1)
    assert stats == Stats(1, 0, 0, 0, 0, 0)
