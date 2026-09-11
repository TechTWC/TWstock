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
from experiments.fundamental_oos_shadow.live import (  # noqa: E402
    ExistingContractLiveSource,
    run_live_collection,
    run_scheduled_collection,
    validate_snapshot_tree,
)
from experiments.fundamental_oos_shadow.scheduled import (  # noqa: E402
    verify_collector_runtime_freeze,
)


DEFAULT_CONTRACT = ROOT / "config/fundamental_oos_shadow_v0_1.json"
DEFAULT_FIXTURE = ROOT / "tests/fixtures/fundamental_oos_shadow/oos_a_valid_fixture.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="OOS-C shared manual/scheduled collection and offline validation."
    )
    result.add_argument("--dry-run", action="store_true", help="Validate a fixture without writing")
    result.add_argument("--validate-ledger", action="store_true", help="Verify both immutable ledgers")
    result.add_argument("--validate-freeze", action="store_true", help="Verify frozen model/universe identity")
    result.add_argument("--fixture", action="store_true", help="Use the tracked synthetic OOS-A fixture")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Explicitly run bounded manual OOS-C collection")
    mode.add_argument(
        "--scheduled-run",
        action="store_true",
        help="Run the scheduled-safe OOS-C collector with freeze and write guards",
    )
    result.add_argument(
        "--symbols",
        help="Optional comma-separated frozen-universe subset for an authorized smoke test",
    )
    result.add_argument("--validate-snapshots", action="store_true", help="Verify immutable snapshot manifests")
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    contract = load_contract(args.contract)
    if not any(
        (
            args.live,
            args.scheduled_run,
            args.dry_run,
            args.validate_ledger,
            args.validate_freeze,
            args.fixture,
            args.validate_snapshots,
        )
    ):
        raise SystemExit(
            "Select --live, --scheduled-run, --dry-run, --validate-ledger, --validate-freeze, "
            "--validate-snapshots, or --fixture"
        )
    report: dict[str, object] = {
        "stage": "OOS-C",
        "live_collection_enabled": contract["live_collection_enabled"],
        "live_collection_mode": contract["live_collection_mode"],
        "scheduled_collection_prepared": contract["scheduled_collection_prepared"],
        "scheduled_collection_active": contract["scheduled_collection_active"],
        "historical_backfill_enabled": contract["historical_backfill_enabled"],
        "outcome_calculation_enabled": contract["outcome_calculation_enabled"],
        "network_requests": {"MOPS": 0, "FinMind": 0, "TWSE": 0, "Other": 0},
    }
    if args.live:
        selected = None
        if args.symbols:
            selected = [item.strip() for item in args.symbols.split(",") if item.strip()]
        report.update(
            run_live_collection(
                ROOT,
                contract,
                ExistingContractLiveSource(),
                symbols=selected,
            )
        )
    if args.scheduled_run:
        selected = None
        if args.symbols:
            selected = [item.strip() for item in args.symbols.split(",") if item.strip()]
        report.update(
            run_scheduled_collection(
                ROOT,
                contract,
                ExistingContractLiveSource(),
                symbols=selected,
            )
        )
    if args.validate_freeze:
        report["freeze"] = verify_freeze(ROOT, contract)
        report["collector_runtime_freeze"] = verify_collector_runtime_freeze(
            ROOT, manifest_path=str(contract["collector_runtime_manifest_path"])
        )
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
    if args.validate_snapshots:
        report["snapshot_manifests_validated"] = validate_snapshot_tree(
            ROOT / str(contract["raw_snapshot_root"])
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
