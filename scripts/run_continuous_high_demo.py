from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.breakout_tracker_v5 import PriceBar
from experiments.continuous_high_monitor import (
    ContinuousHighMonitor,
    load_config,
    write_feature_csv,
    write_html_report,
    write_timeline_csv,
)


def synthetic_bars() -> list[PriceBar]:
    closes: list[float] = []
    for index in range(290):
        if index < 80:
            close = 100.0 - index * 0.15
        elif index < 125:
            close = 88.0 + (index - 80) * 0.24
        elif index < 235:
            close = 98.8 + (index - 125) * 0.43
        elif index < 255:
            close = 146.1 + (index - 235) * 1.15
        else:
            close = 169.1 - (index - 255) * 1.55
        closes.append(round(close, 2))

    output: list[PriceBar] = []
    start = date(2025, 1, 2)
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        open_price = (previous + close) / 2
        volume = 1_000_000.0 + (index % 11) * 20_000.0
        if index in (126, 180, 238):
            volume *= 2.0
        output.append(
            PriceBar(
                symbol="SYNTHETIC.TW",
                trade_date=start + timedelta(days=index),
                open=open_price,
                high=max(open_price, close) * 1.008,
                low=min(open_price, close) * 0.992,
                close=close,
                volume=volume,
            )
        )
    return output


def main() -> None:
    config = load_config(
        ROOT / "experiments/continuous_high_monitor/default_config.json"
    )
    bars = synthetic_bars()
    result = ContinuousHighMonitor(config).run(bars)
    output = ROOT / "outputs/experiments/continuous_high_monitor"
    output.mkdir(parents=True, exist_ok=True)
    write_html_report(
        path=output / "demo.html",
        bars=bars,
        result=result,
        config=config,
    )
    write_timeline_csv(result, output / "timeline.csv")
    write_feature_csv(result, config, output / "features.csv")
    print(
        f"wrote {output / 'demo.html'}; "
        f"first discovery={result.first_discovery_date}; events={len(result.events)}"
    )


if __name__ == "__main__":
    main()
