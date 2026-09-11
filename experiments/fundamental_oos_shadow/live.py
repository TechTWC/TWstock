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
from .scheduled import (
    assert_clean_scheduler_start,
    assert_scheduled_write_allowlist,
    verify_collector_code_freeze,
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


def _immutable_json(path: Path, payload: object) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if path.exists():
        if path.read_bytes() != encoded:
            raise ContractError(f"Immutable JSON identity conflict: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ContractError(f"Concurrent immutable JSON conflict: {path}")


class CandidateRegistry:
    """Mutable state machine; emitted signals remain authoritative in the ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("registry_version") not in {"OOS-B-1", "OOS-C-1"} or not isinstance(
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
                "registry_version": "OOS-C-1",
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


class ContentAddressedSourceStore:
    """Deduplicate source bytes against both OOS-C blobs and OOS-B snapshots."""

    def __init__(self, root: Path, legacy_snapshot_root: Path) -> None:
        self.root = root
        self.legacy_snapshot_root = legacy_snapshot_root
        self._legacy_index: dict[str, str] | None = None

    def _index_legacy(self) -> dict[str, str]:
        if self._legacy_index is not None:
            return self._legacy_index
        index: dict[str, str] = {}
        if self.legacy_snapshot_root.exists():
            SnapshotStore(self.legacy_snapshot_root).validate_all()
            base = self.legacy_snapshot_root.parents[2]
            for path in sorted(self.legacy_snapshot_root.glob("*/*/raw.bin")):
                digest = sha256_bytes(path.read_bytes())
                index.setdefault(digest, path.relative_to(base).as_posix())
        self._legacy_index = index
        return index

    def put(self, raw: bytes) -> dict[str, Any]:
        digest = sha256_bytes(raw)
        path = self.root / f"{digest}.bin"
        reference = path.relative_to(self.root.parents[2]).as_posix()
        if path.exists():
            if sha256_bytes(path.read_bytes()) != digest:
                raise ContractError(f"Source blob hash mismatch: {path}")
            return {
                "source_sha256": digest,
                "changed": False,
                "status": "UNCHANGED_SOURCE",
                "previous_snapshot_reference": reference,
                "new_blob": False,
            }
        legacy = self._index_legacy().get(digest)
        if legacy is not None:
            return {
                "source_sha256": digest,
                "changed": False,
                "status": "UNCHANGED_SOURCE",
                "previous_snapshot_reference": legacy,
                "new_blob": False,
            }
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if sha256_bytes(path.read_bytes()) != digest:
                raise ContractError(f"Concurrent source blob conflict: {path}")
            return {
                "source_sha256": digest,
                "changed": False,
                "status": "UNCHANGED_SOURCE",
                "previous_snapshot_reference": reference,
                "new_blob": False,
            }
        if sha256_bytes(path.read_bytes()) != digest:
            raise ContractError(f"Source blob write verification failed: {path}")
        return {
            "source_sha256": digest,
            "changed": True,
            "status": "CHANGED_SOURCE",
            "previous_snapshot_reference": None,
            "blob_reference": reference,
            "new_blob": True,
        }

    def validate_all(self) -> int:
        if not self.root.exists():
            return 0
        count = 0
        for path in sorted(self.root.glob("*.bin")):
            expected = path.stem
            if len(expected) != 64 or sha256_bytes(path.read_bytes()) != expected:
                raise ContractError(f"Source blob hash mismatch: {path}")
            count += 1
        return count


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


def _source_audit(
    store: ContentAddressedSourceStore,
    *,
    source_type: str,
    symbol: str,
    retrieved_at: str,
    source_identifier: str,
    raw: bytes,
) -> dict[str, Any]:
    stored = store.put(raw)
    return {
        "source_type": source_type,
        "symbol": symbol,
        "retrieved_at": retrieved_at,
        "source_identifier": source_identifier,
        **stored,
    }


def run_collection(
    root: Path,
    contract: Mapping[str, Any],
    source: LiveSource,
    *,
    mode: str,
    now: Callable[[], datetime] = utc_now,
    symbols: Iterable[str] | None = None,
    enforce_repository_guards: bool = True,
) -> dict[str, Any]:
    """Run the one shared manual/scheduled OOS-C collection engine."""

    mode = mode.upper()
    if mode not in {"MANUAL", "SCHEDULED"}:
        raise ContractError("Unknown collection mode")
    if not contract.get("live_collection_enabled"):
        raise ContractError("LIVE_COLLECTION_DISABLED")
    if contract.get("live_collection_mode") != "MANUAL_AND_SCHEDULED_ENGINE":
        raise ContractError("OOS-C requires the shared manual and scheduled engine")
    if not contract.get("scheduled_collection_prepared"):
        raise ContractError("SCHEDULED_COLLECTION_NOT_PREPARED")
    if contract.get("historical_backfill_enabled"):
        raise ContractError("Historical backfill is prohibited")
    if contract.get("outcome_calculation_enabled"):
        raise ContractError("Outcome calculation is prohibited in OOS-C")
    if mode == "SCHEDULED" and enforce_repository_guards:
        assert_clean_scheduler_start(root)

    verify_freeze(root, contract)
    code_freeze = verify_collector_code_freeze(root, contract)
    signal_path = root / str(contract["signal_ledger_path"])
    outcome_path = root / str(contract["outcome_ledger_path"])
    existing_signals = validate_signal_ledger(signal_path)
    validate_outcome_ledger(outcome_path)
    registry = CandidateRegistry(root / str(contract["pending_candidate_registry_path"]))
    registry_before = registry.path.read_bytes() if registry.path.exists() else b""
    signal_before = signal_path.read_bytes() if signal_path.exists() else b""
    candidates = registry.load()
    legacy_root = root / str(contract["raw_snapshot_root"])
    SnapshotStore(legacy_root).validate_all()
    source_store = ContentAddressedSourceStore(
        root / str(contract["source_blob_root"]), legacy_root
    )
    before_blobs = source_store.validate_all()
    universe = pd.read_csv(root / str(contract["frozen_universe_path"]), dtype=str).fillna("")
    universe_by_symbol = {
        str(row["symbol"]): row for row in universe.to_dict(orient="records")
    }
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
    source_audits: list[dict[str, Any]] = []
    symbol_audits: dict[str, dict[str, Any]] = {
        symbol: {
            "symbol": symbol,
            "scan_timestamp": started_at,
            "candidate_statuses": [],
            "formal_signal_result": "NO_SIGNAL",
        }
        for symbol in requested
    }
    report: dict[str, Any] = {
        "stage": "OOS-C",
        "collection_mode": mode,
        "run_timestamp": started_at,
        "post_oos_mops_filings_discovered": 0,
        "formal_signals_appended": 0,
        "financial_exclusions_observed": 0,
        "pre_oos_exclusions_observed": 0,
        "duplicate_idempotent_skips": 0,
        "source_conflicts": 0,
        "failed_closed_events": 0,
        "changed_source_bodies": 0,
        "unchanged_source_bodies": 0,
        "new_blobs": 0,
        "duplicate_blobs_avoided": 0,
        "collector_code_freeze": code_freeze,
    }

    def audit_source(audit: dict[str, Any]) -> None:
        source_audits.append(audit)
        if audit["changed"]:
            report["changed_source_bodies"] += 1
        else:
            report["unchanged_source_bodies"] += 1
            report["duplicate_blobs_avoided"] += 1
        if audit["new_blob"]:
            report["new_blobs"] += 1

    for symbol in requested:
        try:
            scan, raw = source.scan_mops(symbol)
            if str(scan.get("response_sha256")) != sha256_bytes(raw):
                raise ContractError("MOPS response hash mismatch")
            scan_audit = _source_audit(
                source_store,
                source_type="MOPS",
                symbol=symbol,
                retrieved_at=str(scan["retrieval_timestamp"]),
                source_identifier=str(scan["source_url"]),
                raw=raw,
            )
            audit_source(scan_audit)
            symbol_audits[symbol].update(
                {
                    "source_hash": scan_audit["source_sha256"],
                    "source_status": scan_audit["status"],
                    "previous_snapshot_reference": scan_audit.get(
                        "previous_snapshot_reference"
                    ),
                }
            )
            records = list(scan.get("records", []))
            conflicts = len(scan.get("source_conflicts", []))
            report["source_conflicts"] += conflicts
            if conflicts:
                raise ContractError("MOPS source conflict")
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
            report.setdefault("run_errors", []).append(
                f"{symbol}:{type(exc).__name__}:{exc}"
            )

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
        if candidate["status"] in {
            "FINANCIAL_EXCLUDED",
            "SIGNAL_EMITTED",
            "FAILED_CLOSED",
            "SOURCE_CONFLICT",
        }:
            if candidate["status"] == "SIGNAL_EMITTED":
                report["duplicate_idempotent_skips"] += 1
            continue
        try:
            if "locked_signal" not in candidate:
                financial, financial_raw = source.financial(
                    str(candidate["symbol"]), history_start, today
                )
                financial_audit = _source_audit(
                    source_store,
                    source_type="FINANCIAL",
                    symbol=str(candidate["symbol"]),
                    retrieved_at=str(financial["retrieved_at"]),
                    source_identifier=str(financial["source_identifier"]),
                    raw=financial_raw,
                )
                audit_source(financial_audit)
                candidate["financial_source_retrieved_at"] = financial["retrieved_at"]
                candidate["financial_source_hash"] = financial_audit["source_sha256"]
                if not _financial_complete(financial["normalized"], str(candidate["period_end"])):
                    candidate["status"] = "PENDING_FINANCIAL_DATA"
                    continue

                valuation, valuation_raw = source.valuation(
                    str(candidate["symbol"]), history_start, today
                )
                valuation_audit = _source_audit(
                    source_store,
                    source_type="VALUATION",
                    symbol=str(candidate["symbol"]),
                    retrieved_at=str(valuation["retrieved_at"]),
                    source_identifier=str(valuation["source_identifier"]),
                    raw=valuation_raw,
                )
                audit_source(valuation_audit)
                candidate["valuation_source_retrieved_at"] = valuation["retrieved_at"]
                candidate["valuation_source_hash"] = valuation_audit["source_sha256"]
                if not _valuation_complete(valuation["normalized"]):
                    candidate["status"] = "PENDING_VALUATION_DATA"
                    continue

                generated_at = timestamp(now())
                candidate["locked_signal"] = _build_locked_signal(
                    candidate,
                    financial,
                    str(financial_audit["source_sha256"]),
                    valuation,
                    str(valuation_audit["source_sha256"]),
                    contract,
                    model_config,
                    generated_at,
                )
                candidate["first_complete_data_locked_at"] = generated_at

            locked = dict(candidate["locked_signal"])
            session, session_raw = source.sessions(
                str(candidate["symbol"]), history_start, today
            )
            session_audit = _source_audit(
                source_store,
                source_type="MARKET_SESSION",
                symbol=str(candidate["symbol"]),
                retrieved_at=str(session["retrieved_at"]),
                source_identifier=str(session["source_identifier"]),
                raw=session_raw,
            )
            audit_source(session_audit)
            first_trade = _next_common_session(
                str(locked["information_cutoff_timestamp"]), session
            )
            if first_trade is None:
                candidate["status"] = "PENDING_SESSION"
                continue
            locked["first_trade_date"] = first_trade
            same_period = [
                item
                for item in existing_signals
                if item["symbol"] == locked["symbol"]
                and item["period_end"] == locked["period_end"]
            ]
            if locked["event_id"] in {item["event_id"] for item in existing_signals}:
                candidate["status"] = "SIGNAL_EMITTED"
                report["duplicate_idempotent_skips"] += 1
                continue
            if same_period:
                locked["status"] = "SUPERSEDING_EVENT"
                locked["supersedes_event_id"] = same_period[-1]["event_id"]
                locked["reason_codes"] = list(locked["reason_codes"]) + [
                    "SOURCE_CORRECTION"
                ]
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
            symbol_audits[str(candidate["symbol"])]["formal_signal_result"] = "SIGNAL_EMITTED"
        except (ContractError, LedgerError) as exc:
            message = str(exc).lower()
            if "conflict" in message or "mismatch" in message or "corrupt" in message:
                candidate["status"] = "SOURCE_CONFLICT"
                key = "source_conflicts"
            elif "locked_signal" in candidate:
                candidate["status"] = "PENDING_SESSION"
                key = "failed_closed_events"
            elif candidate.get("financial_source_hash"):
                candidate["status"] = "PENDING_VALUATION_DATA"
                key = "failed_closed_events"
            else:
                candidate["status"] = "PENDING_FINANCIAL_DATA"
                key = "failed_closed_events"
            report[key] += 1
            candidate["last_failure_reason"] = str(exc)
            report.setdefault("run_errors", []).append(
                f"{candidate_id}:{type(exc).__name__}:{exc}"
            )
        except Exception as exc:
            if "locked_signal" in candidate:
                candidate["status"] = "PENDING_SESSION"
            elif candidate.get("financial_source_hash"):
                candidate["status"] = "PENDING_VALUATION_DATA"
            else:
                candidate["status"] = "PENDING_FINANCIAL_DATA"
            candidate["last_failure_reason"] = f"{type(exc).__name__}:{exc}"
            report["failed_closed_events"] += 1
            report.setdefault("run_errors", []).append(
                f"{candidate_id}:{type(exc).__name__}:{exc}"
            )
        finally:
            registry.save(candidates)

    signal_records = validate_signal_ledger(signal_path)
    validate_outcome_ledger(outcome_path)
    source_store.validate_all()
    for symbol, audit in symbol_audits.items():
        audit["candidate_statuses"] = sorted(
            {
                str(candidate["status"])
                for candidate in candidates.values()
                if str(candidate["symbol"]) == symbol
            }
        )
    counts = {status: 0 for status in CANDIDATE_STATUSES}
    for candidate in candidates.values():
        counts[str(candidate["status"])] += 1
    report["network_requests"] = dict(source.network_requests)
    report["source_blob_total"] = source_store.validate_all()
    report["new_blobs"] = report["source_blob_total"] - before_blobs
    report["signal_ledger_total_records"] = len(signal_records)
    report["hash_chain_validation"] = "PASS"
    report["pending_candidates"] = {
        status: counts[status]
        for status in (
            "MOPS_DISCOVERED",
            "PENDING_FINANCIAL_DATA",
            "PENDING_VALUATION_DATA",
            "PENDING_SESSION",
        )
    }
    registry_changed = registry.path.read_bytes() != registry_before
    signal_changed = signal_path.read_bytes() != signal_before
    report["commit_worthy_state_change"] = bool(
        registry_changed or signal_changed or report["new_blobs"]
    )
    run_id = canonical_hash(
        {
            "started_at": started_at,
            "mode": mode,
            "symbols": requested,
            "source_hashes": [audit["source_sha256"] for audit in source_audits],
        }
    )[:32]
    run_manifest = {
        "manifest_version": "OOS-C-1",
        "run_id": run_id,
        "stage": "OOS-C",
        "mode": mode,
        "started_at": started_at,
        "frozen_model_hash": contract["frozen_model_hash"],
        "frozen_universe_hash": contract["frozen_universe_hash"],
        "oos_start_timestamp": contract["oos_start_timestamp"],
        "collector_code_freeze_sha": contract["collector_code_freeze_sha"],
        "outcome_calculation_enabled": False,
        "symbols": [symbol_audits[symbol] for symbol in requested],
        "sources": source_audits,
        "summary": {
            key: report[key]
            for key in (
                "changed_source_bodies",
                "unchanged_source_bodies",
                "new_blobs",
                "duplicate_blobs_avoided",
                "post_oos_mops_filings_discovered",
                "formal_signals_appended",
                "commit_worthy_state_change",
            )
        },
        "failure_count": len(report.get("run_errors", [])),
    }
    run_path = root / str(contract["run_manifest_root"]) / f"{run_id}.json"
    _immutable_json(run_path, run_manifest)
    report["run_manifest_path"] = run_path.relative_to(root).as_posix()
    if mode == "SCHEDULED" and enforce_repository_guards:
        report["scheduled_changed_paths"] = assert_scheduled_write_allowlist(root)
    if report.get("run_errors"):
        raise ContractError(
            "SCHEDULED_COLLECTION_FAILED_CLOSED"
            if mode == "SCHEDULED"
            else "LIVE_COLLECTION_FAILED_CLOSED"
        )
    return report


def run_live_collection(
    root: Path,
    contract: Mapping[str, Any],
    source: LiveSource,
    *,
    now: Callable[[], datetime] = utc_now,
    symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    return run_collection(
        root, contract, source, mode="MANUAL", now=now, symbols=symbols
    )


def run_scheduled_collection(
    root: Path,
    contract: Mapping[str, Any],
    source: LiveSource,
    *,
    now: Callable[[], datetime] = utc_now,
    symbols: Iterable[str] | None = None,
    enforce_repository_guards: bool = True,
) -> dict[str, Any]:
    return run_collection(
        root,
        contract,
        source,
        mode="SCHEDULED",
        now=now,
        symbols=symbols,
        enforce_repository_guards=enforce_repository_guards,
    )


def validate_snapshot_tree(root: Path) -> int:
    return SnapshotStore(root).validate_all()
