"""Shared foundation for the PipelineService package (ARCH-4 slice 9).

``StampingUnavailableError`` lives here so both the raise sites (StampingMixin) and
``run``\'s ``except`` clause (service.py) import the SAME class object.
"""

from __future__ import annotations


class StampingUnavailableError(RuntimeError):
    """Raised when a stamping stage (QR/watermark) is requested but no real backend exists.

    Distinct from a genuine stamping *failure*: it signals that the feature was
    enabled while the platform ships only a placeholder backend, so the stage must
    be recorded as an honest ``skipped`` (not ``success`` — which would imply the
    PDF was stamped — and not ``error`` — which would imply a malfunction).
    """
