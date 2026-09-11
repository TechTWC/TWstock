from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, Mapping, Protocol

import pandas as pd

from experiments.fundamental_quality_valuation.data import (
    fetch_finmind_dataset,
    normalize_market,
    normalize_quarterly,
)
from experiments.fundamental_quality_valuation.engine import classify_security
from experiments.fundamental_quality_valuation.models import SectorLogic, SecurityData
from experiments.fundamental_quality_valuation.mops import (
    fetch_mops_filing_year,
    parse_mops_filing_candidates,
    select_mops_filings,
)
from experiments.fundamental_quality_valuation.stage_a import canonical_hash

from .ledger import (
    ContractError,
    LedgerError,
    append_signal_record,
    validate_outcome_ledger,
    validate_signal_ledger,
    verify_freeze,
)


CANDIDATE_STATUSES = {
    "MOPS_DISCOVERED",
    "PENDING_FINANCIAL_DATA",
    "PENDING_VALUATION_DATA",
    "PENDING_SESSION",
    "READY_FOR_SIGNAL",
    "SIGNAL_EMITTED",
    "FINANCIAL_EXCLUDED",
    "SOURCE_CONFLICT",
    "FAILED_CLOSED",
}
FINANCIAL_DATASETS = (
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockCashFlowsStatement",
)
VALUATION_DATASETS = ("TaiwanStockPrice", "TaiwanStockPER")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError("Live timestamps require an explicit timezone")
    return value.isoformat()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def filing_identity_hash(filing: Mapping[str, Any]) -> str:
    """Stable filing identity independent of all-year response and retrieval time."""

    fields = {
        "symbol": str(filing["symbol"]),
        "period_end": str(filing["period_end"]),
        "announcement_timestamp": str(filing["announcement_timestamp"]),
        "source_identifier": str(filing["source_identifier"]),
        "document_kind": str(filing.get("document_kind", "")),
        "file_size_bytes": filing.get("file_size_bytes"),
        "correction_status": str(filing.get("correction_status", "")),
    }
    return canonical_hash(fields)


def stable_event_id(filing: Mapping[str, Any], contract: Mapping[str, Any]) -> str:
    identity = canonical_hash(
        {
            "symbol": str(filing["symbol"]),
            "period_end": str(filing["period_end"]),
            "mops_filing_identity_hash": filing_identity_hash(filing),
            "model_hash": contract["frozen_model_hash"],
            "universe_hash": contract["frozen_universe_hash"],
        }
    )
    return f"0050-FQV-OOS-{identity[:32]}"


def conservative_cutoff(*values: str) -> str:
    parsed = [datetime.fromisoformat(value) for value in values]
    if not parsed or any(value.tzinfo is None or value.utcoffset() is None for value in parsed):
        raise ContractError("Availability timestamps require explicit timezones")
    return max(parsed).isoformat()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


class CandidateRegistry:
    """Mutable state machine; emitted signals remain authoritative in the ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("registry_version") != "OOS-B-1" or not isinstance(
            payload.get("candidates"), list
        ):
            raise ContractError("Invalid OOS pending candidate registry")
        result: dict[str, dict[str, Any]] = {}
        for candidate in payload["candidates"]:
            self.validate(candidate)
            candidate_id = str(candidate["candidate_id"])
            if candidate_id in result:
                raise ContractError("Duplicate candidate_id in registry")
            result[candidate_id] = dict(candidate)
        return result

    @staticmethod
    def validate(candidate: Mapping[str, Any]) -> None:
        required = {
            "candidate_id",
            "event_id",
            "symbol",
            "company",
            "period_end",
            "fiscal_year",
            "fiscal_quarter",
            "mops_announcement_timestamp",
            "mops_retrieved_at",
            "mops_source_hash",
            "mops_filing_identity_hash",
            "status",
        }
        missing = required - candidate.keys()
        if missing:
            raise ContractError(f"Candidate missing fields: {', '.join(sorted(missing))}")
        if candidate["status"] not in CANDIDATE_STATUSES:
            raise ContractError("Unknown pending candidate status")

    def save(self, candidates: Mapping[str, Mapping[str, Any]]) -> None:
        for candidate in candidates.values():
            self.validate(candidate)
        _atomic_json(
            self.path,
            {
                "registry_version": "OOS-B-1",
                "candidates": [dict(candidates[key]) for key in sorted(candidates)],
            },
        )

    def upsert_first_seen(
        self,
        candidates: dict[str, dict[str, Any]],
        candidate: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.validate(candidate)
        candidate_id = str(candidate["candidate_id"])
        existing = candidates.get(candidate_id)
        if existing is not None:
            immutable = {
                "event_id",
                "symbol",
                "period_end",
                "mops_announcement_timestamp",
                "mops_source_hash",
                "mops_filing_identity_hash",
            }
            if any(existing.get(key) != candidate.get(key) for key in immutable):
                raise ContractError("Candidate identity conflict")
            return existing
        candidates[candidate_id] = dict(candidate)
        return candidates[candidate_id]


class SnapshotStore:
    """Write immutable, content-addressed retrieval snapshots and verify manifests."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self,
        *,
        identity: str,
        snapshot_type: str,
        retrieved_at: str,
        source_identifier: str,
        raw: bytes,
        normalized: object | None = None,
    ) -> dict[str, Any]:
        raw_hash = sha256_bytes(raw)
        snapshot_id = canonical_hash(
            {
                "identity": identity,
                "snapshot_type": snapshot_type,
                "retrieved_at": retrieved_at,
                "source_identifier": source_identifier,
                "raw_sha256": raw_hash,
            }
        )
        directory = self.root / identity / f"{snapshot_type.lower()}-{snapshot_id[:20]}"
        manifest_path = directory / "manifest.json"
        if directory.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.validate_manifest(manifest_path)
            return manifest
        directory.mkdir(parents=True, exist_ok=False)
        raw_path = directory / "raw.bin"
        with raw_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        files = {"raw.bin": raw_hash}
        if normalized is not None:
            normalized_bytes = canonical_bytes(normalized)
            normalized_path = directory / "normalized.json"
            with normalized_path.open("xb") as handle:
                handle.write(normalized_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            files["normalized.json"] = sha256_bytes(normalized_bytes)
        manifest = {
            "manifest_version": "OOS-B-1",
            "snapshot_id": snapshot_id,
            "event_or_candidate_identity": identity,
            "snapshot_type": snapshot_type,
            "retrieved_at": retrieved_at,
            "source_identifier": source_identifier,
            "source_sha256": raw_hash,
            "files": files,
        }
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.validate_manifest(manifest_path)
        return manifest

    @staticmethod
    def validate_manifest(path: Path) -> dict[str, Any]:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "manifest_version",
            "snapshot_id",
            "event_or_candidate_identity",
            "snapshot_type",
            "retrieved_at",
            "source_identifier",
            "source_sha256",
            "files",
        }
        if required - manifest.keys() or manifest["manifest_version"] != "OOS-B-1":
            raise ContractError(f"Invalid snapshot manifest: {path}")
        if not isinstance(manifest["files"], dict) or not manifest["files"]:
            raise ContractError(f"Empty snapshot manifest: {path}")
        for relative, expected in manifest["files"].items():
            candidate = path.parent / relative
            if candidate.parent != path.parent or not candidate.is_file():
                raise ContractError(f"Snapshot manifest path is unsafe or missing: {relative}")
            if sha256_bytes(candidate.read_bytes()) != expected:
                raise ContractError(f"Snapshot hash mismatch: {candidate}")
        if manifest["files"].get("raw.bin") != manifest["source_sha256"]:
            raise ContractError(f"Snapshot source hash mismatch: {path}")
        return manifest

    def validate_all(self) -> int:
        if not self.root.exists():
            return 0
        manifests = sorted(self.root.glob("*/*/manifest.json"))
        for path in manifests:
            self.validate_manifest(path)
        return len(manifests)


class LiveSource(Protocol):
    network_requests: dict[str, int]

    def scan_mops(self, symbol: str) -> tuple[dict[str, Any], bytes]: ...

    def financial(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]: ...

    def valuation(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]: ...

    def sessions(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]: ...


class ExistingContractLiveSource:
    """Manual-only adapter over the already-reviewed MOPS and FinMind contracts."""

    def __init__(self) -> None:
        self.network_requests = {"MOPS": 0, "FinMind": 0, "TWSE": 0, "Other": 0}

    def scan_mops(self, symbol: str) -> tuple[dict[str, Any], bytes]:
        with tempfile.TemporaryDirectory(prefix="twstock-oos-mops-") as name:
            cache = Path(name)
            self.network_requests["MOPS"] += 1
            result = fetch_mops_filing_year(
                symbol, None, cache, refresh=True, attempts=1, timeout=60
            )
            raw = (cache / f"{symbol}_ALL_AVAILABLE_YEARS_MOPS_t57sb01.html").read_bytes()
        all_candidates = parse_mops_filing_candidates(
            raw.decode("big5", errors="replace"),
            source_url=result.source_url,
            retrieval_timestamp=result.retrieval_timestamp,
            response_sha256=result.response_sha256,
        )
        _, decisions = select_mops_filings(all_candidates)
        return {
            "symbol": result.symbol,
            "source_url": result.source_url,
            "retrieval_timestamp": result.retrieval_timestamp,
            "response_sha256": result.response_sha256,
            "fetch_status": result.fetch_status,
            "reason_code": result.reason_code,
            "records": [record.to_dict() for record in result.records],
            "source_conflicts": [
                {
                    "symbol": decision.symbol,
                    "fiscal_year": decision.fiscal_year,
                    "fiscal_quarter": decision.fiscal_quarter,
                    "reason_code": decision.reason_code,
                }
                for decision in decisions
                if decision.status == "CONFLICT_FAIL_CLOSED"
            ],
        }, raw

    def _finmind_bundle(
        self, symbol: str, datasets: Iterable[str], start: str, end: str
    ) -> tuple[dict[str, Any], bytes]:
        payloads: dict[str, Any] = {}
        with tempfile.TemporaryDirectory(prefix="twstock-oos-finmind-") as name:
            cache = Path(name)
            for dataset in datasets:
                self.network_requests["FinMind"] += 1
                payloads[dataset] = fetch_finmind_dataset(
                    dataset, symbol, start, end, cache, refresh=True, attempts=1
                )
        return payloads, canonical_bytes(payloads)

    def financial(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]:
        payloads, raw = self._finmind_bundle(symbol, FINANCIAL_DATASETS, start, end)
        normalized = normalize_quarterly(
            payloads["TaiwanStockFinancialStatements"]["data"],
            payloads["TaiwanStockBalanceSheet"]["data"],
            payloads["TaiwanStockCashFlowsStatement"]["data"],
            {"q1": 60, "q2": 60, "q3": 60, "q4": 90},
        )
        return {
            "retrieved_at": _latest_retrieval(payloads),
            "source_identifier": "FinMind:v4:financial-normalized-contract-0.1.1",
            "payloads": payloads,
            "normalized": _frame_records(normalized),
        }, raw

    def valuation(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]:
        payloads, raw = self._finmind_bundle(symbol, VALUATION_DATASETS, start, end)
        normalized = normalize_market(
            payloads["TaiwanStockPrice"]["data"], payloads["TaiwanStockPER"]["data"]
        )
        return {
            "retrieved_at": _latest_retrieval(payloads),
            "source_identifier": "FinMind:v4:price+PER",
            "payloads": payloads,
            "normalized": _frame_records(normalized),
        }, raw

    def sessions(self, symbol: str, start: str, end: str) -> tuple[dict[str, Any], bytes]:
        stock, stock_raw = self._finmind_bundle(symbol, ("TaiwanStockPrice",), start, end)
        benchmark, benchmark_raw = self._finmind_bundle("0050", ("TaiwanStockPrice",), start, end)
        stock_dates = sorted({str(row["date"]) for row in stock["TaiwanStockPrice"]["data"]})
        benchmark_dates = sorted(
            {str(row["date"]) for row in benchmark["TaiwanStockPrice"]["data"]}
        )
        common = sorted(set(stock_dates) & set(benchmark_dates))
        payload = {
            "retrieved_at": max(_latest_retrieval(stock), _latest_retrieval(benchmark)),
            "source_identifier": "FinMind:v4:TaiwanStockPrice:stock+0050-common-session",
            "twse_sessions": common,
            "stock_sessions": stock_dates,
            "benchmark_sessions": benchmark_dates,
        }
        return payload, stock_raw + b"\n" + benchmark_raw


def _latest_retrieval(payloads: Mapping[str, Any]) -> str:
    values = [
        str(payload.get("_research_metadata", {}).get("retrieved_at"))
        for payload in payloads.values()
        if payload.get("_research_metadata", {}).get("retrieved_at")
    ]
    if not values:
        raise ContractError("Source did not supply a retrieval timestamp")
    return max(values)


def _json_value(value: object) -> object:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[union-attr]
    return value


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _frame(records: Iterable[Mapping[str, Any]], date_field: str) -> pd.DataFrame:
    frame = pd.DataFrame(list(records))
    if not frame.empty:
        for field in {date_field, "period_end", "announcement_date", "available_date", "date"}:
            if field in frame:
                frame[field] = pd.to_datetime(frame[field], errors="coerce").dt.date
    return frame


def _source_hash(raw: bytes) -> str:
    return sha256_bytes(raw)


def _candidate_from_filing(
    filing: Mapping[str, Any], universe_row: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    event_id = stable_event_id(filing, contract)
    return {
        "candidate_id": event_id,
        "event_id": event_id,
        "symbol": str(filing["symbol"]),
        "company": str(universe_row["company"]),
        "sector_logic": str(universe_row["sector_logic"]),
        "peer_group": str(universe_row.get("peer_group", "UNCLASSIFIED")),
        "financial_subtype": str(universe_row.get("financial_subtype", "")) or None,
        "period_end": str(filing["period_end"]),
        "fiscal_year": int(filing["fiscal_year"]),
        "fiscal_quarter": int(filing["fiscal_quarter"]),
        "mops_announcement_timestamp": str(filing["announcement_timestamp"]),
        "mops_retrieved_at": str(filing["retrieval_timestamp"]),
        "mops_source_hash": str(filing["response_sha256"]),
        "mops_filing_identity_hash": filing_identity_hash(filing),
        "mops_source_identifier": str(filing["source_identifier"]),
        "status": (
            "FINANCIAL_EXCLUDED"
            if str(universe_row["sector_logic"]) == "FINANCIAL"
            else "MOPS_DISCOVERED"
        ),
    }


def _financial_complete(normalized: list[dict[str, Any]], period_end: str) -> bool:
    matching = [row for row in normalized if str(row.get("period_end")) == period_end]
    if len(matching) != 1:
        return False
    required = ("ttm_revenue", "ttm_eps", "equity", "ttm_cfo")
    return all(matching[0].get(field) is not None for field in required)


def _valuation_complete(normalized: list[dict[str, Any]]) -> bool:
    if not normalized:
        return False
    latest = normalized[-1]
    return latest.get("close") is not None and any(
        latest.get(field) is not None for field in ("PER", "PBR", "dividend_yield")
    )


def _build_locked_signal(
    candidate: Mapping[str, Any],
    financial: Mapping[str, Any],
    financial_hash: str,
    valuation: Mapping[str, Any],
    valuation_hash: str,
    contract: Mapping[str, Any],
    model_config: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    quarterly = _frame(financial["normalized"], "period_end")
    market = _frame(valuation["normalized"], "date")
    candidate_period = datetime.fromisoformat(str(candidate["period_end"])).date()
    quarterly = quarterly[quarterly["period_end"] <= candidate_period].copy()
    target = quarterly["period_end"] == candidate_period
    quarterly.loc[target, "announcement_date"] = datetime.fromisoformat(
        str(candidate["mops_announcement_timestamp"])
    ).date()
    quarterly.loc[target, "available_date"] = datetime.fromisoformat(generated_at).date()
    quarterly.loc[target, "availability_method"] = "MOPS_EXACT"
    quarterly.loc[target, "timestamp_confidence"] = "verified_source_field"
    security = SecurityData(
        symbol=str(candidate["symbol"]),
        company=str(candidate["company"]),
        industry=str(candidate.get("peer_group", "UNCLASSIFIED")),
        sector_logic=SectorLogic(str(candidate["sector_logic"])),
        quarterly=quarterly,
        market=market,
        peer_group=str(candidate.get("peer_group", "UNCLASSIFIED")),
        financial_subtype=candidate.get("financial_subtype"),
        source="FinMind v4 normalized + official MOPS availability",
        source_metadata={
            "retrieval_date": financial["retrieved_at"],
            "source_version": "FinMind API v4 normalized-contract-0.1.1",
            "source_hash": financial_hash,
        },
        data_flags=[],
    )
    generated_date = datetime.fromisoformat(generated_at).date()
    result = classify_security(
        security, generated_date, dict(model_config), market_as_of=generated_date
    )
    cutoff = conservative_cutoff(
        str(candidate["mops_announcement_timestamp"]),
        str(candidate["mops_retrieved_at"]),
        str(financial["retrieved_at"]),
        str(valuation["retrieved_at"]),
        generated_at,
    )
    return {
        "event_id": str(candidate["event_id"]),
        "symbol": str(candidate["symbol"]),
        "company": str(candidate["company"]),
        "sector_logic": str(candidate["sector_logic"]),
        "predictive_eligible": True,
        "period_end": str(candidate["period_end"]),
        "mops_announcement_timestamp": str(candidate["mops_announcement_timestamp"]),
        "mops_retrieved_at": str(candidate["mops_retrieved_at"]),
        "financial_source_retrieved_at": str(financial["retrieved_at"]),
        "valuation_source_retrieved_at": str(valuation["retrieved_at"]),
        "information_cutoff_timestamp": cutoff,
        "signal_generated_at": generated_at,
        "signal_date": datetime.fromisoformat(cutoff).date().isoformat(),
        "first_trade_date": None,
        "quality": result.quality,
        "fundamental_state": result.fundamental_state,
        "state_detail": result.state_detail,
        "valuation": result.valuation,
        "data_quality": result.data_quality,
        "reason_codes": list(result.reason_codes) or ["FROZEN_MODEL_EXECUTED"],
        "financial_source_hash": financial_hash,
        "mops_source_hash": str(candidate["mops_source_hash"]),
        "valuation_source_hash": valuation_hash,
        "model_hash": str(contract["frozen_model_hash"]),
        "universe_hash": str(contract["frozen_universe_hash"]),
        "status": "ACTIVE_SIGNAL",
        "supersedes_event_id": None,
    }


def _next_common_session(cutoff: str, sessions: Mapping[str, Any]) -> str | None:
    cutoff_date = datetime.fromisoformat(cutoff).date()
    twse = set(sessions.get("twse_sessions", []))
    stock = set(sessions.get("stock_sessions", []))
    benchmark = set(sessions.get("benchmark_sessions", []))
    common = sorted(twse & stock & benchmark)
    if any(datetime.fromisoformat(value).date().weekday() >= 5 for value in common):
        raise ContractError("Session source contains a weekend")
    return next(
        (value for value in common if datetime.fromisoformat(value).date() > cutoff_date), None
    )


def run_live_collection(
    root: Path,
    contract: Mapping[str, Any],
    source: LiveSource,
    *,
    now: Callable[[], datetime] = utc_now,
    symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Perform one bounded manual live run; no caller other than --live invokes it."""

    if not contract.get("live_collection_enabled"):
        raise ContractError("LIVE_COLLECTION_DISABLED")
    if contract.get("live_collection_mode") != "MANUAL_ONLY":
        raise ContractError("Live collection must remain MANUAL_ONLY")
    if contract.get("scheduled_collection_enabled"):
        raise ContractError("Scheduled collection is prohibited in OOS-B")
    if contract.get("historical_backfill_enabled"):
        raise ContractError("Historical backfill is prohibited")
    if contract.get("outcome_calculation_enabled"):
        raise ContractError("Outcome calculation is prohibited in OOS-B")

    verify_freeze(root, contract)
    signal_path = root / str(contract["signal_ledger_path"])
    outcome_path = root / str(contract["outcome_ledger_path"])
    existing_signals = validate_signal_ledger(signal_path)
    validate_outcome_ledger(outcome_path)
    registry = CandidateRegistry(root / str(contract["pending_candidate_registry_path"]))
    candidates = registry.load()
    snapshots = SnapshotStore(root / str(contract["raw_snapshot_root"]))
    universe = pd.read_csv(root / str(contract["frozen_universe_path"]), dtype=str).fillna("")
    universe_by_symbol = {str(row["symbol"]): row for row in universe.to_dict(orient="records")}
    default_symbols = [
        symbol
        for symbol, row in universe_by_symbol.items()
        if str(row["sector_logic"]) != "FINANCIAL"
    ]
    requested = sorted(set(symbols if symbols is not None else default_symbols))
    if any(symbol not in universe_by_symbol for symbol in requested):
        raise ContractError("Live scan symbol is outside frozen universe")
    if len(requested) > int(contract["frozen_cohort_count"]):
        raise ContractError("Live scan exceeds frozen universe bound")
    if symbols is None and len(requested) != int(contract["expected_non_financial"]):
        raise ContractError("Default live scan must equal the frozen 38-stock non-financial cohort")

    started_at = timestamp(now())
    start = datetime.fromisoformat(str(contract["oos_start_timestamp"]))
    report: dict[str, Any] = {
        "live_smoke_run_timestamp": started_at,
        "post_oos_mops_filings_discovered": 0,
        "formal_signals_appended": 0,
        "financial_exclusions_observed": 0,
        "pre_oos_exclusions_observed": 0,
        "duplicate_idempotent_skips": 0,
        "raw_snapshots_created": 0,
        "source_conflicts": 0,
        "failed_closed_events": 0,
    }
    before_manifests = snapshots.validate_all()

    for symbol in requested:
        try:
            scan, raw = source.scan_mops(symbol)
            scan_identity = f"scan-{sha256_bytes((started_at + ':' + symbol).encode())[:24]}"
            snapshots.write(
                identity=scan_identity,
                snapshot_type="MOPS",
                retrieved_at=str(scan["retrieval_timestamp"]),
                source_identifier=str(scan["source_url"]),
                raw=raw,
                normalized=scan,
            )
            records = list(scan.get("records", []))
            report["source_conflicts"] += len(scan.get("source_conflicts", []))
            report["pre_oos_exclusions_observed"] += sum(
                datetime.fromisoformat(str(item["announcement_timestamp"])) < start
                for item in records
            )
            for filing in records:
                if datetime.fromisoformat(str(filing["announcement_timestamp"])) < start:
                    continue
                report["post_oos_mops_filings_discovered"] += 1
                candidate = _candidate_from_filing(filing, universe_by_symbol[symbol], contract)
                current = registry.upsert_first_seen(candidates, candidate)
                if current["status"] == "FINANCIAL_EXCLUDED":
                    report["financial_exclusions_observed"] += 1
        except Exception as exc:
            report["failed_closed_events"] += 1
            report.setdefault("run_errors", []).append(f"{symbol}:{type(exc).__name__}")
        registry.save(candidates)

    model_config = json.loads(
        (root / str(contract["frozen_model_config_path"])).read_text(encoding="utf-8")
    )
    today = now().date().isoformat()
    history_start = str(model_config.get("history_start", "2016-01-01"))
    ordered_candidate_ids = sorted(
        candidates,
        key=lambda candidate_id: (
            str(candidates[candidate_id]["symbol"]),
            str(candidates[candidate_id]["period_end"]),
            str(candidates[candidate_id]["mops_announcement_timestamp"]),
            candidate_id,
        ),
    )
    for candidate_id in ordered_candidate_ids:
        candidate = candidates[candidate_id]
        if candidate["status"] in {"FINANCIAL_EXCLUDED", "SIGNAL_EMITTED", "FAILED_CLOSED", "SOURCE_CONFLICT"}:
            if candidate["status"] == "SIGNAL_EMITTED":
                report["duplicate_idempotent_skips"] += 1
            continue
        try:
            if "locked_signal" not in candidate:
                financial, financial_raw = source.financial(
                    str(candidate["symbol"]), history_start, today
                )
                financial_manifest = snapshots.write(
                    identity=candidate_id,
                    snapshot_type="FINANCIAL",
                    retrieved_at=str(financial["retrieved_at"]),
                    source_identifier=str(financial["source_identifier"]),
                    raw=financial_raw,
                    normalized=financial["normalized"],
                )
                candidate["financial_source_retrieved_at"] = financial["retrieved_at"]
                candidate["financial_source_hash"] = financial_manifest["source_sha256"]
                if not _financial_complete(financial["normalized"], str(candidate["period_end"])):
                    candidate["status"] = "PENDING_FINANCIAL_DATA"
                    continue

                valuation, valuation_raw = source.valuation(
                    str(candidate["symbol"]), history_start, today
                )
                valuation_manifest = snapshots.write(
                    identity=candidate_id,
                    snapshot_type="VALUATION",
                    retrieved_at=str(valuation["retrieved_at"]),
                    source_identifier=str(valuation["source_identifier"]),
                    raw=valuation_raw,
                    normalized=valuation["normalized"],
                )
                candidate["valuation_source_retrieved_at"] = valuation["retrieved_at"]
                candidate["valuation_source_hash"] = valuation_manifest["source_sha256"]
                if not _valuation_complete(valuation["normalized"]):
                    candidate["status"] = "PENDING_VALUATION_DATA"
                    continue

                generated_at = timestamp(now())
                candidate["locked_signal"] = _build_locked_signal(
                    candidate,
                    financial,
                    str(financial_manifest["source_sha256"]),
                    valuation,
                    str(valuation_manifest["source_sha256"]),
                    contract,
                    model_config,
                    generated_at,
                )
                candidate["first_complete_data_locked_at"] = generated_at

            locked = dict(candidate["locked_signal"])
            session, session_raw = source.sessions(str(candidate["symbol"]), history_start, today)
            snapshots.write(
                identity=candidate_id,
                snapshot_type="MARKET_SESSION",
                retrieved_at=str(session["retrieved_at"]),
                source_identifier=str(session["source_identifier"]),
                raw=session_raw,
                normalized=session,
            )
            first_trade = _next_common_session(str(locked["information_cutoff_timestamp"]), session)
            if first_trade is None:
                candidate["status"] = "PENDING_SESSION"
                continue
            locked["first_trade_date"] = first_trade
            same_period = [
                item
                for item in existing_signals
                if item["symbol"] == locked["symbol"] and item["period_end"] == locked["period_end"]
            ]
            if locked["event_id"] in {item["event_id"] for item in existing_signals}:
                candidate["status"] = "SIGNAL_EMITTED"
                report["duplicate_idempotent_skips"] += 1
                continue
            if same_period:
                locked["status"] = "SUPERSEDING_EVENT"
                locked["supersedes_event_id"] = same_period[-1]["event_id"]
                locked["reason_codes"] = list(locked["reason_codes"]) + ["SOURCE_CORRECTION"]
            candidate["status"] = "READY_FOR_SIGNAL"
            appended = append_signal_record(
                signal_path,
                locked,
                contract,
                twse_sessions=session["twse_sessions"],
                stock_sessions=session["stock_sessions"],
                benchmark_sessions=session["benchmark_sessions"],
            )
            existing_signals.append(appended)
            candidate["status"] = "SIGNAL_EMITTED"
            candidate["emitted_record_hash"] = appended["record_hash"]
            report["formal_signals_appended"] += 1
        except (ContractError, LedgerError) as exc:
            candidate["status"] = "SOURCE_CONFLICT" if "conflict" in str(exc).lower() else "FAILED_CLOSED"
            key = "source_conflicts" if candidate["status"] == "SOURCE_CONFLICT" else "failed_closed_events"
            report[key] += 1
            candidate["failure_reason"] = str(exc)
        except Exception as exc:
            candidate["status"] = "FAILED_CLOSED"
            candidate["failure_reason"] = f"{type(exc).__name__}:{exc}"
            report["failed_closed_events"] += 1
        finally:
            registry.save(candidates)

    report["network_requests"] = dict(source.network_requests)
    report["raw_snapshots_created"] = snapshots.validate_all() - before_manifests
    report["signal_ledger_total_records"] = len(validate_signal_ledger(signal_path))
    report["hash_chain_validation"] = "PASS"
    counts = {status: 0 for status in CANDIDATE_STATUSES}
    for candidate in candidates.values():
        counts[str(candidate["status"])] += 1
    report["pending_candidates"] = {
        status: counts[status]
        for status in (
            "MOPS_DISCOVERED",
            "PENDING_FINANCIAL_DATA",
            "PENDING_VALUATION_DATA",
            "PENDING_SESSION",
        )
    }
    return report


def validate_snapshot_tree(root: Path) -> int:
    return SnapshotStore(root).validate_all()
