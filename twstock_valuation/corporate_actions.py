"""Corporate-action normalization on a latest-share-count basis."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Sequence

from twstock_data.errors import DataValidationError
from twstock_data.sources.mops_face_value_change import (
    FACE_VALUE_COVERAGE_PROVEN, FACE_VALUE_LEGAL_START, FaceValueCoverageProof,
)
from twstock_data.sources.twse_corporate_actions import (
    CAPITAL_REDUCTION_HISTORY_START,
    CORPORATE_ACTION_REVIEW_REQUIRED, NORMALIZATION_READY,
    NORMALIZATION_REVIEW_REQUIRED,
    SUPPORTED_NORMALIZATION_ACTION_TYPES,
    CorporateActionEvent, mark_conflicting_duplicates,
)
from twstock_data.sources.twse_valuation import ValuationObservation
from .pe_river import DEFAULT_MULTIPLES, distribution

NO_ACTION = "NO_ACTION"
NORMALIZED = "NORMALIZED"
PE_UNAVAILABLE = "PE_UNAVAILABLE"
REFERENCE_PERIOD_UNAVAILABLE = "REFERENCE_PERIOD_UNAVAILABLE"
NORMALIZED_PERCENTILE_COMPLETE = "NORMALIZED_PERCENTILE_COMPLETE"
NORMALIZED_PERCENTILE_INCOMPLETE = "NORMALIZED_PERCENTILE_INCOMPLETE"
SOURCE_COVERAGE_INCOMPLETE = "SOURCE_COVERAGE_INCOMPLETE"
NORMALIZATION_COVERAGE_START = CAPITAL_REDUCTION_HISTORY_START
TPEX_NORMALIZATION_COVERAGE_START = date(2013, 1, 1)
CAPITAL_REDUCTION_COVERAGE_REASON = (
    "capital reduction official source coverage begins 2011-01-01")


@dataclass(frozen=True)
class NormalizedRiverObservation:
    observation: ValuationObservation
    raw_implied_reference_eps: float | None
    pending_share_factor: float | None
    normalized_pe: float | None
    normalized_reference_eps_local: float | None
    future_share_factor: float | None
    adjusted_close: float | None
    adjusted_reference_eps: float | None
    adjusted_band_prices: tuple[float | None, ...]
    normalization_status: str
    applied_pending_events: tuple[date, ...] = ()
    applied_future_events: tuple[date, ...] = ()


def _product(events: Sequence[CorporateActionEvent]) -> float:
    result = 1.0
    for event in events:
        if (event.share_factor is None or event.status != NORMALIZATION_READY
                or event.action_type not in SUPPORTED_NORMALIZATION_ACTION_TYPES):
            raise DataValidationError("unresolved event cannot enter normalization")
        result *= event.share_factor
    if not math.isfinite(result) or result <= 0:
        raise DataValidationError("invalid combined corporate-action factor")
    return result


def normalize_for_corporate_actions(
        observations: Sequence[ValuationObservation],
        events: Sequence[CorporateActionEvent], multiples=DEFAULT_MULTIPLES,
        analysis_end_date: date | None = None):
    if not observations:
        raise ValueError("no historical observations")
    multiples = tuple(float(value) for value in multiples)
    if (not multiples or any(not math.isfinite(value) or value <= 0 for value in multiples)
            or tuple(sorted(set(multiples))) != multiples):
        raise ValueError("multiples must be distinct, increasing, positive finite numbers")
    symbol = observations[0].symbol
    previous = None
    for observation in observations:
        if observation.symbol != symbol:
            raise ValueError("mixed symbols")
        if previous is not None and observation.trade_date <= previous:
            raise ValueError("observations must have unique chronological dates")
        if not math.isfinite(observation.official_close) or observation.official_close <= 0:
            raise ValueError("invalid official close")
        previous = observation.trade_date
    events = mark_conflicting_duplicates(events)
    if any(event.symbol != symbol for event in events):
        raise DataValidationError("corporate-action symbol mismatch")
    end = analysis_end_date or observations[-1].trade_date
    if end < observations[-1].trade_date:
        raise ValueError("analysis end precedes latest observation")

    market = observations[0].market or "TWSE"
    coverage_start = (TPEX_NORMALIZATION_COVERAGE_START
                      if market == "TPEX" else NORMALIZATION_COVERAGE_START)
    output = []
    for observation in observations:
        official_pe = observation.official_pe
        valid_pe = (official_pe is not None and math.isfinite(official_pe)
                    and official_pe > 0)
        raw_eps = observation.official_close / official_pe if valid_pe else None
        if observation.trade_date < coverage_start:
            output.append(NormalizedRiverObservation(
                observation=observation,
                raw_implied_reference_eps=raw_eps,
                pending_share_factor=None,
                normalized_pe=None,
                normalized_reference_eps_local=None,
                future_share_factor=None,
                adjusted_close=None,
                adjusted_reference_eps=None,
                adjusted_band_prices=(None,) * len(multiples),
                normalization_status=SOURCE_COVERAGE_INCOMPLETE,
            ))
            continue
        past_events = [event for event in events if event.effective_date <= observation.trade_date]
        future_events = [event for event in events
                         if observation.trade_date < event.effective_date <= end]
        unresolved_future = [event for event in future_events if event.status != NORMALIZATION_READY]
        pending = []
        unresolved_pending = []
        reference_end = observation.reference_period_end
        if past_events and reference_end is None:
            status = REFERENCE_PERIOD_UNAVAILABLE
        else:
            pending = [event for event in past_events
                       if reference_end is not None and reference_end < event.effective_date]
            unresolved_pending = [event for event in pending if event.status != NORMALIZATION_READY]
            status = NORMALIZED if pending or future_events else NO_ACTION
        unresolved = unresolved_pending + unresolved_future
        if unresolved:
            status = (NORMALIZATION_REVIEW_REQUIRED
                      if any(event.status == NORMALIZATION_REVIEW_REQUIRED
                             for event in unresolved)
                      else CORPORATE_ACTION_REVIEW_REQUIRED)

        pending_factor = None if status in (
            REFERENCE_PERIOD_UNAVAILABLE, CORPORATE_ACTION_REVIEW_REQUIRED,
            NORMALIZATION_REVIEW_REQUIRED) else _product(pending)
        future_factor = None if unresolved_future else _product(future_events)
        normalized_pe = official_pe * pending_factor if valid_pe and pending_factor is not None else None
        local_eps = (observation.official_close / normalized_pe
                     if normalized_pe is not None else None)
        adjusted_close = (observation.official_close / future_factor
                          if future_factor is not None else None)
        adjusted_eps = (local_eps / future_factor
                        if local_eps is not None and future_factor is not None else None)
        bands = tuple(adjusted_eps * multiple if adjusted_eps is not None else None
                      for multiple in multiples)
        # A row without official PE has no EPS or normalized PE to resolve.
        # Keep it explicitly unavailable rather than allowing a missing
        # reference-period field on that same row to block the distribution.
        # Relevant unresolved events still mark every affected valid-PE row.
        if not valid_pe:
            status = PE_UNAVAILABLE
        output.append(NormalizedRiverObservation(
            observation=observation, raw_implied_reference_eps=raw_eps,
            pending_share_factor=pending_factor, normalized_pe=normalized_pe,
            normalized_reference_eps_local=local_eps, future_share_factor=future_factor,
            adjusted_close=adjusted_close, adjusted_reference_eps=adjusted_eps,
            adjusted_band_prices=bands, normalization_status=status,
            applied_pending_events=tuple(event.effective_date for event in pending),
            applied_future_events=tuple(event.effective_date for event in future_events),
        ))
    return tuple(output)


def normalized_distributions(rows: Sequence[NormalizedRiverObservation]) -> dict:
    if not rows:
        raise ValueError("empty normalized report")
    raw_values = [row.observation.official_pe for row in rows]
    latest_raw = next((value for value in reversed(raw_values)
                       if value is not None and math.isfinite(value) and value > 0), None)
    normalized_values = [row.normalized_pe for row in rows]
    latest_normalized = next((value for value in reversed(normalized_values)
                              if value is not None and math.isfinite(value) and value > 0), None)
    incomplete = any(
        row.normalization_status == SOURCE_COVERAGE_INCOMPLETE
        or (row.observation.official_pe is not None
            and row.normalization_status in (
                CORPORATE_ACTION_REVIEW_REQUIRED, NORMALIZATION_REVIEW_REQUIRED,
                REFERENCE_PERIOD_UNAVAILABLE))
        for row in rows)
    return {
        "raw_pe_distribution": distribution(raw_values, latest_raw),
        "normalized_pe_distribution": (
            None if incomplete else distribution(normalized_values, latest_normalized)),
        "normalization_status": (
            NORMALIZED_PERCENTILE_INCOMPLETE if incomplete
            else NORMALIZED_PERCENTILE_COMPLETE),
    }


def build_corporate_action_metadata(
        rows: Sequence[NormalizedRiverObservation],
        events: Sequence[CorporateActionEvent], base_metadata: dict,
        request_results=(), *, face_value_proof: FaceValueCoverageProof) -> dict:
    """Attach serializable raw/normalized audit evidence to report metadata."""
    if not rows:
        raise ValueError("empty normalized report")
    proof_end_required = date.fromisoformat(base_metadata["requested_end_cutoff"])
    proof_start_required = max(
        rows[0].observation.trade_date, FACE_VALUE_LEGAL_START)
    if face_value_proof.symbol != rows[0].observation.symbol:
        raise DataValidationError("face-value proof symbol mismatch")
    observation_market = rows[0].observation.market or "TWSE"
    if face_value_proof.market != observation_market:
        raise DataValidationError("face-value proof market mismatch")
    if proof_end_required >= FACE_VALUE_LEGAL_START and (
            face_value_proof.query_start > proof_start_required
            or face_value_proof.query_end < proof_end_required):
        raise DataValidationError("face-value proof interval does not cover report")
    distributions = normalized_distributions(rows)
    latest = next((row for row in reversed(rows) if row.normalized_pe is not None), None)
    unavailable = [row for row in rows if row.observation.official_pe is None]
    unavailable_preserved = all(
        row.raw_implied_reference_eps is None
        and row.normalized_pe is None
        and row.normalized_reference_eps_local is None
        and row.adjusted_reference_eps is None
        and all(value is None for value in row.adjusted_band_prices)
        for row in unavailable
    )

    def event_payload(event: CorporateActionEvent) -> dict:
        return {
            "symbol": event.symbol,
            "effective_date": event.effective_date.isoformat(),
            "resume_date": event.resume_date.isoformat() if event.resume_date else None,
            "action_type": event.action_type,
            "reduction_type": event.reduction_type,
            "share_factor": event.share_factor,
            "cash_return_per_share": event.cash_return_per_share,
            "bonus_share_rate": event.bonus_share_rate,
            "cash_rights_rate": event.cash_rights_rate,
            "pre_event_close": event.pre_event_close,
            "official_reference_price": event.official_reference_price,
            "status": event.status,
            "derived": event.derived,
            "derivation_formula": event.derivation_formula,
            "source_url": event.source_url,
            "detail_source_url": event.detail_source_url,
            "retrieved_at": event.retrieved_at,
            "raw_hash": event.raw_hash,
            "old_par_value": event.old_par_value,
            "new_par_value": event.new_par_value,
            "mops_DATE1": event.mops_date1,
            "mops_SKEY": event.mops_skey,
            "coverage_proof_status": event.coverage_proof_status,
            "source_fields": dict(event.source_fields),
        }

    action_payloads = [event_payload(event) for event in events]
    face_value_complete = face_value_proof.status == FACE_VALUE_COVERAGE_PROVEN
    normalized_distribution = (
        distributions["normalized_pe_distribution"] if face_value_complete else None)
    has_uncertified_rows = any(
        row.normalization_status == SOURCE_COVERAGE_INCOMPLETE for row in rows)
    incomplete_reasons = []
    if has_uncertified_rows:
        incomplete_reasons.append(CAPITAL_REDUCTION_COVERAGE_REASON)
    if not face_value_complete:
        incomplete_reasons.append(
            f"face-value-change per-symbol coverage is {face_value_proof.status}")
    return {
        **base_metadata,
        "schema_version": "TWSTOCK-PE-RIVER-PDF-002",
        "report_title": (
            (f"{base_metadata['canonical_symbol']} | {base_metadata['market']} "
             f"Corporate-Action Adjusted PE River")
            if base_metadata.get("market") == "TPEX" else
            f"{base_metadata['symbol']} | Corporate-Action Adjusted PE River"),
        "raw_pe_distribution": distributions["raw_pe_distribution"],
        "normalized_pe_distribution": normalized_distribution,
        "normalization_status": (
            NORMALIZED_PERCENTILE_INCOMPLETE
            if normalized_distribution is None else NORMALIZED),
        "normalization_coverage_start": (
            TPEX_NORMALIZATION_COVERAGE_START if observation_market == "TPEX"
            else NORMALIZATION_COVERAGE_START).isoformat(),
        "normalization_incomplete_reason": (
            "; ".join(incomplete_reasons) if incomplete_reasons else None),
        "face_value_change_coverage_status": face_value_proof.status,
        "face_value_change_coverage_start": face_value_proof.query_start.isoformat(),
        "face_value_change_coverage_end": face_value_proof.query_end.isoformat(),
        "face_value_change_result_count": face_value_proof.result_count,
        "face_value_change_detail_count": face_value_proof.detail_count,
        "face_value_change_rowset_hash": face_value_proof.rowset_hash,
        "face_value_change_detail_manifest_hash": face_value_proof.detail_manifest_hash,
        "face_value_change_retrieved_at": face_value_proof.retrieved_at,
        "face_value_change_failure_reason": face_value_proof.failure_reason,
        "latest_normalized_pe_date": (
            latest.observation.trade_date.isoformat() if latest else None),
        "latest_normalized_pe": latest.normalized_pe if latest else None,
        "latest_financial_report_period": (
            latest.observation.financial_report_period_raw if latest else None),
        "latest_pending_share_factor": latest.pending_share_factor if latest else None,
        "latest_future_share_factor": latest.future_share_factor if latest else None,
        "latest_adjusted_close": rows[-1].adjusted_close,
        "normalized_valid_pe_observation_count": sum(
            row.normalized_pe is not None for row in rows),
        "normalized_missing_pe_count": sum(
            row.normalized_pe is None for row in rows),
        "unavailable_pe_invariant": {
            "official_unavailable_count": len(unavailable),
            "preserved_blank_count": sum(
                row.raw_implied_reference_eps is None
                and row.normalized_pe is None
                and row.normalized_reference_eps_local is None
                and row.adjusted_reference_eps is None
                and all(value is None for value in row.adjusted_band_prices)
                for row in unavailable),
            "passed": unavailable_preserved,
            "policy": "No forward fill, backward fill, interpolation, or fabricated PE.",
        },
        "corporate_action_mode": "LATEST_SHARE_COUNT",
        "corporate_actions": action_payloads,
        "corporate_action_events": action_payloads,
        "supported_action_count": sum(
            event.status == NORMALIZATION_READY
            and event.action_type in SUPPORTED_NORMALIZATION_ACTION_TYPES
            for event in events),
        "unsupported_action_count": sum(
            event.status != NORMALIZATION_READY
            or event.action_type not in SUPPORTED_NORMALIZATION_ACTION_TYPES
            for event in events),
        "latest_official_pe": base_metadata.get("latest_pe"),
        "raw_pe_percentile": distributions["raw_pe_distribution"]["current_percentile"],
        "normalized_pe_percentile": (
            normalized_distribution["current_percentile"]
            if normalized_distribution is not None else None),
        "corporate_action_request_results": list(request_results),
        "normalization_semantics": (
            "Share-count changes are normalized to the latest share basis. "
            "Official PE and raw implied EPS remain retained for audit."),
        "cash_distribution_semantics": (
            "Cash distributions are not total-return adjusted."),
    }
