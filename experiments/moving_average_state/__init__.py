"""Point-in-time classic moving-average trend-state baseline."""

from .engine import MovingAverageStateEngine
from .models import (
    LongTermContext,
    MAStateConfig,
    MAStateEvent,
    MAStateObservation,
    MAStateResult,
    TrendState,
)
from .report import (
    render_core_ma_svg,
    render_html_report,
    render_long_term_ma_svg,
    write_outputs,
)

__all__ = [
    "LongTermContext",
    "MAStateConfig",
    "MAStateEvent",
    "MAStateObservation",
    "MAStateResult",
    "MovingAverageStateEngine",
    "TrendState",
    "render_core_ma_svg",
    "render_html_report",
    "render_long_term_ma_svg",
    "write_outputs",
]
