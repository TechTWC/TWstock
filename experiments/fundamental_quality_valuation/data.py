from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .models import SectorLogic, SecurityData
from .pit import derive_financial_available_date


FINMIND_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"
YAHOO_TIMESERIES_ENDPOINT = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries"
YAHOO_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart"
TWSE_CURRENT_VALUATION_ENDPOINT = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
FINMIND_DATASETS = (
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockCashFlowsStatement",
    "TaiwanStockPER",
    "TaiwanStockPrice",
)


class ResearchDataError(RuntimeError):
    pass


def _safe_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchDataError(f"Invalid cached JSON: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ResearchDataError(f"Cached payload has no data list: {path}")
    return payload


def fetch_finmind_dataset(
    dataset: str,
    symbol: str,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    attempts: int = 3,
) -> dict[str, Any]:
    if dataset not in FINMIND_DATASETS:
        raise ValueError(f"Unsupported research dataset: {dataset}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}_{dataset}.json"
    if path.exists() and not refresh:
        return _read_json(path)

    query = urlencode(
        {
            "dataset": dataset,
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    url = f"{FINMIND_ENDPOINT}?{query}"
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "TWstock-research/0.1"})
            with urlopen(request, timeout=120) as response:
                payload = json.load(response)
            if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
                raise ResearchDataError(
                    f"FinMind {dataset}/{symbol}: {payload.get('msg', 'invalid response')}"
                )
            payload["_research_metadata"] = {
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source": "FinMind v4",
                "dataset": dataset,
                "data_id": symbol,
                "requested_start": start_date,
                "requested_end": end_date,
            }
            temporary = path.with_suffix(".json.part")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
            return payload
        except Exception as exc:  # retry transport and explicit vendor failures
            error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise ResearchDataError(f"Unable to fetch {dataset}/{symbol}: {error}")


def fetch_stock_info(cache_dir: Path, *, refresh: bool = False) -> dict[str, dict[str, str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "TaiwanStockInfo.json"
    if not path.exists() or refresh:
        request = Request(
            f"{FINMIND_ENDPOINT}?{urlencode({'dataset': 'TaiwanStockInfo'})}",
            headers={"User-Agent": "TWstock-research/0.1"},
        )
        with urlopen(request, timeout=120) as response:
            payload = json.load(response)
        if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
            raise ResearchDataError("Unable to fetch TaiwanStockInfo")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rows = _read_json(path)["data"]
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        symbol = str(row.get("stock_id", ""))
        if symbol:
            result[symbol] = {
                "company": str(row.get("stock_name", "")),
                "industry": str(row.get("industry_category", "")),
                "market": str(row.get("type", "")),
            }
    return result


def _pivot(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    selected = [row for row in rows if row.get("date") and row.get("type")]
    if not selected:
        return pd.DataFrame()
    frame = pd.DataFrame(selected)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    return frame.pivot_table(index="date", columns="type", values="value", aggfunc="last")


def _first_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    for alias in aliases:
        if alias in frame.columns:
            return pd.to_numeric(frame[alias], errors="coerce")
    return pd.Series(math.nan, index=frame.index, dtype=float)


def _sum_columns(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    columns = [column for column in aliases if column in frame.columns]
    if not columns:
        return pd.Series(math.nan, index=frame.index, dtype=float)
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    return values.sum(axis=1, min_count=1)


def _quarterize_ytd(series: pd.Series) -> pd.Series:
    if series.empty:
        return series.astype(float)
    result = pd.Series(index=series.index, dtype=float)
    for _, group in series.sort_index().groupby(series.index.year):
        previous = math.nan
        previous_ordinal: int | None = None
        for timestamp, value in group.items():
            current = _safe_float(value)
            ordinal = int(timestamp.year * 4 + ((timestamp.month - 1) // 3))
            if not math.isfinite(current):
                result.loc[timestamp] = math.nan
            elif math.isfinite(previous) and previous_ordinal is not None and ordinal == previous_ordinal + 1:
                result.loc[timestamp] = current - previous
            elif timestamp.month == 3:
                result.loc[timestamp] = current
            else:
                result.loc[timestamp] = math.nan
            previous = current
            previous_ordinal = ordinal
    return result.sort_index()


def _rolling_ttm(series: pd.Series) -> pd.Series:
    return series.rolling(window=4, min_periods=4).sum()


def _announcement_date_map(*row_sets: list[dict[str, Any]]) -> dict[date, date]:
    """Use a source-supplied date only when explicitly present and ordered."""

    result: dict[date, date] = {}
    for rows in row_sets:
        for row in rows:
            period = pd.to_datetime(row.get("date"), errors="coerce")
            raw = next(
                (
                    row.get(key)
                    for key in ("announcement_date", "filing_date", "available_date")
                    if row.get(key)
                ),
                None,
            )
            announced = pd.to_datetime(raw, errors="coerce")
            if pd.isna(period) or pd.isna(announced) or announced.date() < period.date():
                continue
            result[period.date()] = max(result.get(period.date(), announced.date()), announced.date())
    return result


def _growth(series: pd.Series, periods: int = 4) -> pd.Series:
    previous = series.shift(periods)
    valid = (previous.abs() > 1e-12) & previous.notna() & series.notna()
    result = pd.Series(math.nan, index=series.index, dtype=float)
    result.loc[valid] = series.loc[valid] / previous.loc[valid] - 1.0
    return result


def normalize_quarterly(
    financial_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
    cashflow_rows: list[dict[str, Any]],
    availability_lags: dict[str, int],
) -> pd.DataFrame:
    announcement_dates = _announcement_date_map(financial_rows, balance_rows, cashflow_rows)
    income = _pivot(financial_rows)
    balance = _pivot(balance_rows)
    cashflow = _pivot(cashflow_rows)
    observed_index = income.index.union(balance.index).union(cashflow.index).sort_values()
    if observed_index.empty:
        return pd.DataFrame()
    index = pd.date_range(observed_index.min(), observed_index.max(), freq="QE-DEC")
    output = pd.DataFrame(index=index)

    income = income.reindex(index)
    balance = balance.reindex(index)
    cashflow = cashflow.reindex(index)
    output["revenue"] = _first_column(income, ("Revenue",))
    output["gross_profit"] = _first_column(income, ("GrossProfit",))
    output["operating_income"] = _first_column(income, ("OperatingIncome",))
    output["net_income"] = _first_column(
        income,
        ("IncomeAfterTaxes", "TotalConsolidatedProfitForThePeriod"),
    )
    output["pre_tax_income"] = _first_column(income, ("PreTaxIncome",))
    output["interest_expense"] = _first_column(
        income,
        ("InterestExpense", "FinanceCosts", "InterestExpenseAndFinanceCosts"),
    ).abs()
    output["eps"] = _first_column(income, ("EPS",))
    output["equity"] = _first_column(
        balance,
        ("EquityAttributableToOwnersOfParent", "Equity"),
    )
    output["assets"] = _first_column(balance, ("TotalAssets",))
    output["liabilities"] = _first_column(balance, ("Liabilities",))
    output["current_assets"] = _first_column(balance, ("CurrentAssets",))
    output["current_liabilities"] = _first_column(balance, ("CurrentLiabilities",))
    output["cash"] = _first_column(balance, ("CashAndCashEquivalents",))
    output["debt"] = _sum_columns(
        balance,
        (
            "ShorttermBorrowings",
            "ShortTermBorrowings",
            "CurrentPortionOfLongtermLiabilities",
            "LongtermBorrowings",
            "LongTermBorrowings",
            "BondsPayable",
        ),
    )
    output["retained_earnings"] = _first_column(balance, ("RetainedEarnings",))
    output["ordinary_shares"] = _first_column(balance, ("OrdinaryShare",))
    output["bvps"] = _first_column(
        balance,
        ("BookValuePerShare", "NetValuePerShare"),
    )

    cfo_ytd = _first_column(
        cashflow,
        ("CashFlowsFromOperatingActivities", "NetCashInflowFromOperatingActivities"),
    )
    capex_ytd = _first_column(cashflow, ("PropertyAndPlantAndEquipment",))
    output["cfo"] = _quarterize_ytd(cfo_ytd)
    output["capex"] = -_quarterize_ytd(capex_ytd)
    output.loc[output["capex"] < 0, "capex"] = math.nan
    output["fcf"] = output["cfo"] - output["capex"]

    for column in (
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps",
        "interest_expense",
        "cfo",
        "capex",
        "fcf",
    ):
        output[f"ttm_{column}"] = _rolling_ttm(output[column])
    output["gross_margin"] = output["ttm_gross_profit"] / output["ttm_revenue"]
    output["operating_margin"] = output["ttm_operating_income"] / output["ttm_revenue"]
    output["net_margin"] = output["ttm_net_income"] / output["ttm_revenue"]
    average_equity = (output["equity"] + output["equity"].shift(4)) / 2.0
    average_assets = (output["assets"] + output["assets"].shift(4)) / 2.0
    output["roe"] = output["ttm_net_income"] / average_equity
    output["roa"] = output["ttm_net_income"] / average_assets
    tax_rate = 1.0 - output["ttm_net_income"] / _rolling_ttm(output["pre_tax_income"])
    tax_rate = tax_rate.clip(lower=0.0, upper=0.35)
    invested_capital = output["equity"] + output["debt"] - output["cash"]
    average_invested = (invested_capital + invested_capital.shift(4)) / 2.0
    output["roic"] = output["ttm_operating_income"] * (1.0 - tax_rate) / average_invested
    output.loc[average_invested <= 0, "roic"] = math.nan
    output["cfo_net_income"] = output["ttm_cfo"] / output["ttm_net_income"]
    output["net_debt"] = output["debt"] - output["cash"]
    output["net_debt_equity"] = output["net_debt"] / output["equity"]
    output["debt_equity"] = output["debt"] / output["equity"]
    output["current_ratio"] = output["current_assets"] / output["current_liabilities"]
    output["revenue_yoy"] = _growth(output["ttm_revenue"])
    output["eps_yoy"] = _growth(output["ttm_eps"])
    output["fcf_yoy"] = _growth(output["ttm_fcf"])
    output["operating_margin_change"] = output["operating_margin"] - output["operating_margin"].shift(4)
    output["equity_yoy"] = _growth(output["equity"])
    output.index.name = "period_end"
    output = output.reset_index()
    output["period_end"] = output["period_end"].dt.date
    output["announcement_date"] = output["period_end"].map(announcement_dates)
    output["available_date"] = output.apply(
        lambda row: row["announcement_date"]
        if pd.notna(row["announcement_date"])
        else derive_financial_available_date(
            row["period_end"],
            q1_lag_days=int(availability_lags["q1"]),
            q2_lag_days=int(availability_lags["q2"]),
            q3_lag_days=int(availability_lags["q3"]),
            q4_lag_days=int(availability_lags["q4"]),
        ),
        axis=1,
    )
    output["availability_method"] = np.where(
        output["announcement_date"].notna(), "ACTUAL_ANNOUNCEMENT_DATE", "AVAILABLE_DATE_PROXY"
    )
    output["timestamp_confidence"] = np.where(
        output["announcement_date"].notna(), "verified_source_field", "conservative_proxy"
    )
    output = output.replace([np.inf, -np.inf], np.nan)
    return output.sort_values("period_end").reset_index(drop=True)


def normalize_market(
    price_rows: list[dict[str, Any]], per_rows: list[dict[str, Any]]
) -> pd.DataFrame:
    price = pd.DataFrame(price_rows)
    valuation = pd.DataFrame(per_rows)
    if price.empty:
        return pd.DataFrame(columns=["date", "close", "PER", "PBR", "dividend_yield"])
    price["date"] = pd.to_datetime(price["date"], errors="coerce").dt.date
    price["close"] = pd.to_numeric(price["close"], errors="coerce")
    keep = [column for column in ("date", "close", "max", "min", "Trading_Volume") if column in price.columns]
    output = price[keep].dropna(subset=["date", "close"])
    if not valuation.empty:
        valuation["date"] = pd.to_datetime(valuation["date"], errors="coerce").dt.date
        for column in ("PER", "PBR", "dividend_yield"):
            valuation[column] = pd.to_numeric(valuation[column], errors="coerce")
        output = output.merge(
            valuation[["date", "PER", "PBR", "dividend_yield"]],
            on="date",
            how="left",
        )
    else:
        for column in ("PER", "PBR", "dividend_yield"):
            output[column] = math.nan
    return output.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def load_security_data(
    symbol: str,
    company: str,
    industry: str,
    sector_logic: SectorLogic,
    peer_group: str,
    financial_subtype: str | None,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    availability_lags: dict[str, int],
    *,
    refresh: bool = False,
) -> SecurityData:
    payloads = {
        dataset: fetch_finmind_dataset(
            dataset,
            symbol,
            start_date,
            end_date,
            cache_dir,
            refresh=refresh,
        )
        for dataset in FINMIND_DATASETS
    }
    quarterly = normalize_quarterly(
        payloads["TaiwanStockFinancialStatements"]["data"],
        payloads["TaiwanStockBalanceSheet"]["data"],
        payloads["TaiwanStockCashFlowsStatement"]["data"],
        availability_lags,
    )
    market = normalize_market(
        payloads["TaiwanStockPrice"]["data"],
        payloads["TaiwanStockPER"]["data"],
    )
    metadata_rows = [payload.get("_research_metadata", {}) for payload in payloads.values()]
    retrieved = sorted(str(item.get("retrieved_at")) for item in metadata_rows if item.get("retrieved_at"))
    source_hash = hashlib.sha256(
        json.dumps(
            {dataset: payloads[dataset].get("data", []) for dataset in sorted(payloads)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    flags = ["AVAILABLE_DATE_PROXY", "ANNOUNCEMENT_DATE_UNAVAILABLE"]
    if not market.empty:
        flags.append("UNADJUSTED_PRICE_RETURN")
    return SecurityData(
        symbol=symbol,
        company=company,
        industry=industry,
        sector_logic=sector_logic,
        quarterly=quarterly,
        market=market,
        peer_group=peer_group,
        financial_subtype=financial_subtype,
        source_metadata={
            "retrieval_date": retrieved[-1] if retrieved else None,
            "source_version": "FinMind API v4 normalized-contract-0.1.1",
            "source_hash": source_hash,
        },
        data_flags=flags,
    )


def _download_json(url: str, path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 TWstock-research/0.1"})
    with urlopen(request, timeout=180) as response:
        payload = json.load(response)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _yahoo_fundamental_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    mapping = {
        "quarterlyTotalRevenue": ("financial", "Revenue"),
        "quarterlyGrossProfit": ("financial", "GrossProfit"),
        "quarterlyOperatingIncome": ("financial", "OperatingIncome"),
        "quarterlyNetIncome": ("financial", "IncomeAfterTaxes"),
        "quarterlyPretaxIncome": ("financial", "PreTaxIncome"),
        "quarterlyDilutedEPS": ("financial", "EPS"),
        "quarterlyStockholdersEquity": ("balance", "Equity"),
        "quarterlyTotalAssets": ("balance", "TotalAssets"),
        "quarterlyTotalDebt": ("balance", "LongtermBorrowings"),
        "quarterlyCashCashEquivalentsAndShortTermInvestments": ("balance", "CashAndCashEquivalents"),
        "quarterlyCurrentAssets": ("balance", "CurrentAssets"),
        "quarterlyCurrentLiabilities": ("balance", "CurrentLiabilities"),
        "quarterlyOperatingCashFlow": ("cashflow_direct", "CashFlowsFromOperatingActivities"),
        "quarterlyCapitalExpenditure": ("cashflow_direct", "PropertyAndPlantAndEquipment"),
    }
    output: dict[str, list[dict[str, Any]]] = {"financial": [], "balance": [], "cashflow": []}
    direct_cash: list[tuple[str, str, float]] = []
    result = payload.get("timeseries", {}).get("result", [])
    for series in result:
        types = series.get("meta", {}).get("type", [])
        source_type = types[0] if types else ""
        if source_type not in mapping:
            continue
        group, target_type = mapping[source_type]
        for item in series.get(source_type, []):
            value = item.get("reportedValue", {}).get("raw")
            period_end = item.get("asOfDate")
            parsed = _safe_float(value)
            if not period_end or not math.isfinite(parsed):
                continue
            if group == "cashflow_direct":
                if target_type == "PropertyAndPlantAndEquipment":
                    parsed = -abs(parsed)
                direct_cash.append((period_end, target_type, parsed))
            else:
                output[group].append({"date": period_end, "type": target_type, "value": parsed})
    by_type_year: dict[tuple[str, int], list[tuple[str, float]]] = {}
    for period_end, target_type, value in direct_cash:
        by_type_year.setdefault((target_type, int(period_end[:4])), []).append((period_end, value))
    for (target_type, _), items in by_type_year.items():
        cumulative = 0.0
        for period_end, value in sorted(items):
            cumulative += value
            output["cashflow"].append({"date": period_end, "type": target_type, "value": cumulative})
    return output


def _yahoo_market(payload: dict[str, Any]) -> pd.DataFrame:
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return pd.DataFrame(columns=["date", "close", "max", "min", "PER", "PBR", "dividend_yield"])
    item = result[0]
    timestamps = item.get("timestamp") or []
    quotes = (item.get("indicators", {}).get("quote") or [{}])[0]
    adjusted = (item.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
    rows = []
    for index, timestamp in enumerate(timestamps):
        close_values = quotes.get("close") or []
        if index >= len(close_values) or close_values[index] is None:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, timezone.utc).date(),
                "close": close_values[index],
                "adj_close": adjusted[index] if index < len(adjusted) else math.nan,
                "max": (quotes.get("high") or [None] * len(timestamps))[index],
                "min": (quotes.get("low") or [None] * len(timestamps))[index],
                "PER": math.nan,
                "PBR": math.nan,
                "dividend_yield": math.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def fetch_yahoo_market(
    symbol: str,
    start_date: str,
    end_date: str,
    cache_dir: Path,
) -> pd.DataFrame:
    period1 = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp())
    period2 = int((datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + pd.Timedelta(days=2)).timestamp())
    chart_url = (
        f"{YAHOO_CHART_ENDPOINT}/{symbol}.TW?"
        + urlencode(
            {
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "div,splits",
            }
        )
    )
    return _yahoo_market(_download_json(chart_url, cache_dir / f"{symbol}_YahooChart.json"))


def load_yahoo_fallback_security_data(
    symbol: str,
    company: str,
    industry: str,
    sector_logic: SectorLogic,
    peer_group: str,
    financial_subtype: str | None,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    availability_lags: dict[str, int],
) -> SecurityData:
    """Bounded fallback used only when the FinMind anonymous quota is exhausted.

    Yahoo exposes only a short quarterly window and no historical Taiwan P/E series here.
    The model must therefore return UNKNOWN/N/M where evidence is insufficient.
    """

    period1 = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp())
    period2 = int((datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + pd.Timedelta(days=2)).timestamp())
    types = (
        "quarterlyTotalRevenue,quarterlyGrossProfit,quarterlyOperatingIncome,"
        "quarterlyNetIncome,quarterlyPretaxIncome,quarterlyDilutedEPS,"
        "quarterlyOperatingCashFlow,quarterlyCapitalExpenditure,"
        "quarterlyStockholdersEquity,quarterlyTotalAssets,quarterlyTotalDebt,"
        "quarterlyCashCashEquivalentsAndShortTermInvestments,quarterlyCurrentAssets,"
        "quarterlyCurrentLiabilities"
    )
    fundamental_url = (
        f"{YAHOO_TIMESERIES_ENDPOINT}/{symbol}.TW?"
        + urlencode(
            {
                "symbol": f"{symbol}.TW",
                "type": types,
                "period1": period1,
                "period2": period2,
            }
        )
    )
    fundamentals = _download_json(fundamental_url, cache_dir / f"{symbol}_YahooFundamentals.json")
    rows = _yahoo_fundamental_rows(fundamentals)
    quarterly = normalize_quarterly(rows["financial"], rows["balance"], rows["cashflow"], availability_lags)
    market = fetch_yahoo_market(symbol, start_date, end_date, cache_dir)

    valuation_payload = _download_json(
        TWSE_CURRENT_VALUATION_ENDPOINT,
        cache_dir / "TWSE_BWIBBU_ALL_current.json",
    )
    matching = [row for row in valuation_payload if str(row.get("Code")) == symbol]
    if matching and not market.empty:
        current = matching[-1]
        market.loc[market.index[-1], "PER"] = pd.to_numeric(current.get("PEratio"), errors="coerce")
        market.loc[market.index[-1], "PBR"] = pd.to_numeric(current.get("PBratio"), errors="coerce")
        market.loc[market.index[-1], "dividend_yield"] = pd.to_numeric(current.get("DividendYield"), errors="coerce")
    return SecurityData(
        symbol=symbol,
        company=company,
        industry=industry,
        sector_logic=sector_logic,
        quarterly=quarterly,
        market=market,
        peer_group=peer_group,
        financial_subtype=financial_subtype,
        source="Yahoo Finance fundamentals fallback + TWSE current valuation",
        source_metadata={
            "retrieval_date": datetime.now(timezone.utc).isoformat(),
            "source_version": "Yahoo fundamentals-timeseries/chart + TWSE BWIBBU_ALL",
            "source_hash": hashlib.sha256(
                json.dumps(fundamentals, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        },
        data_flags=[
            "SECONDARY_SOURCE_ONLY",
            "YAHOO_FALLBACK_LIMITED_HISTORY",
            "AVAILABLE_DATE_PROXY",
            "ANNOUNCEMENT_DATE_UNAVAILABLE",
            "HISTORICAL_VALUATION_UNAVAILABLE",
            "ADJUSTED_RETURN_SECONDARY_SOURCE",
            "RAW_PRICE_RETAINED",
        ],
    )


def load_universe(path: Path) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype=str).fillna("")
    required = {
        "symbol",
        "company",
        "sector_logic",
        "peer_group",
        "financial_subtype",
        "universe_as_of",
        "source_note",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ResearchDataError(f"Universe is missing columns: {sorted(missing)}")
    if len(frame) != 50 or frame["symbol"].nunique() != 50:
        raise ResearchDataError("0050 research universe must contain exactly 50 unique symbols")
    return frame.to_dict(orient="records")
