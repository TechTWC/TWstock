"""Point-in-time, paper-inspired consecutive-slope turning detector."""

from .engine import DoubleSlopeTurningEngine
from .comparison import (
    ComparisonResult,
    DetectionPair,
    EventOutcome,
    MethodSummary,
    compare_with_ma_baseline,
)
from .models import (
    DoubleSlopeConfig,
    DoubleSlopeEvent,
    DoubleSlopeObservation,
    DoubleSlopeResult,
    SlopeState,
)
from .report import render_comparison_html, write_comparison_outputs

__all__ = [
    "DoubleSlopeConfig",
    "DoubleSlopeEvent",
    "DoubleSlopeObservation",
    "DoubleSlopeResult",
    "DoubleSlopeTurningEngine",
    "SlopeState",
    "ComparisonResult",
    "DetectionPair",
    "EventOutcome",
    "MethodSummary",
    "compare_with_ma_baseline",
    "render_comparison_html",
    "write_comparison_outputs",
]
