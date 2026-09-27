"""Logging helpers of the cantcp package."""

from __future__ import annotations

import logging

TRACE: int = 5
"""Per-packet tracing level.

Lower than :data:`logging.DEBUG` (10), so tracing can be enabled on its own.
The level name is registered with the :mod:`logging` module.
"""

logging.addLevelName(TRACE, "TRACE")
