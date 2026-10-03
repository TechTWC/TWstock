from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from twstock_data.errors import MarketDataError
from twstock_data.sources.tpex_universe import audit_current_tpex_universe


def run(argv=None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description="Audit current official TPEx ordinary-share universe")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        result = audit_current_tpex_universe(
            transport=transport, timeout=args.timeout, retries=args.retries)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0 if result["acceptance_gate_pass"] else 1
    except (MarketDataError, ValueError, OSError) as exc:
        print(f"TPEx universe audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
