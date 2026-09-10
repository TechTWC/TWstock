from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.fundamental_oos_shadow.ledger import (  # noqa: E402
    load_contract,
    validate_fixture,
    validate_outcome_ledger,
    validate_signal_ledger,
    verify_freeze,
)


DEFAULT_CONTRACT = ROOT / "config/fundamental_oos_shadow_v0_1.json"
DEFAULT_FIXTURE = ROOT / "tests/fixtures/fundamental_oos_shadow/oos_a_valid_fixture.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Bounded OOS-A validation scaffold; live collection is intentionally disabled."
    )
    result.add_argument("--dry-run", action="store_true", help="Validate a fixture without writing")
    result.add_argument("--validate-ledger", action="store_true", help="Verify both immutable ledgers")
    result.add_argument("--validate-freeze", action="store_true", help="Verify frozen model/universe identity")
    result.add_argument("--fixture", action="store_true", help="Use the tracked synthetic OOS-A fixture")
    result.add_argument("--live", action="store_true", help="Reserved for a later authorized stage")
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.live:
        raise SystemExit("LIVE_COLLECTION_NOT_ENABLED_IN_OOS_A")
    if not any((args.dry_run, args.validate_ledger, args.validate_freeze, args.fixture)):
        raise SystemExit("Select --dry-run, --validate-ledger, --validate-freeze, or --fixture")
    contract = load_contract(args.contract)
    report: dict[str, object] = {
        "stage": "OOS-A",
        "live_collection_enabled": False,
        "historical_backfill_enabled": False,
        "network_requests": 0,
    }
    if args.validate_freeze:
        report["freeze"] = verify_freeze(ROOT, contract)
    if args.validate_ledger:
        signal_path = ROOT / str(contract["signal_ledger_path"])
        outcome_path = ROOT / str(contract["outcome_ledger_path"])
        report["signal_ledger_records"] = len(validate_signal_ledger(signal_path))
        report["outcome_ledger_records"] = len(validate_outcome_ledger(outcome_path))
        report["hash_chain"] = "PASS"
    if args.fixture or args.dry_run:
        fixture = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
        signal = validate_fixture(fixture, contract)
        report["fixture"] = {
            "event_id": signal["event_id"],
            "record_hash": signal["record_hash"],
            "validation": "PASS",
            "persisted": False,
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
