"""Frozen, append-only OOS shadow validation foundation for Fundamental v0.1."""

from .ledger import (
    ContractError,
    LedgerError,
    append_outcome_record,
    append_signal_record,
    load_contract,
    validate_fixture,
    validate_outcome_ledger,
    validate_signal_ledger,
    verify_freeze,
)
from .live import (
    CandidateRegistry,
    ContentAddressedSourceStore,
    ExistingContractLiveSource,
    SnapshotStore,
    filing_identity_hash,
    run_live_collection,
    run_scheduled_collection,
    stable_event_id,
    validate_snapshot_tree,
)

__all__ = [
    "ContractError",
    "LedgerError",
    "append_outcome_record",
    "append_signal_record",
    "load_contract",
    "validate_fixture",
    "validate_outcome_ledger",
    "validate_signal_ledger",
    "verify_freeze",
    "CandidateRegistry",
    "ContentAddressedSourceStore",
    "ExistingContractLiveSource",
    "SnapshotStore",
    "filing_identity_hash",
    "run_live_collection",
    "run_scheduled_collection",
    "stable_event_id",
    "validate_snapshot_tree",
]
