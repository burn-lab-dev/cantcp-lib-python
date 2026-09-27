"""Tests of the BadFramePolicy enum."""

from __future__ import annotations

from cantcp.policy import BadFramePolicy


def test_values() -> None:
    assert BadFramePolicy.SKIP.value == "skip"
    assert BadFramePolicy.FAIL.value == "fail"
    assert list(BadFramePolicy) == [BadFramePolicy.SKIP, BadFramePolicy.FAIL]


def test_lookup() -> None:
    assert BadFramePolicy("skip") is BadFramePolicy.SKIP
    assert BadFramePolicy("fail") is BadFramePolicy.FAIL
