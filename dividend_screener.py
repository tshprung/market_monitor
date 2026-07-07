"""Screens dividend candidates against fundamental filters.

Uses yfinance's `.info` dict -- fields are best-effort and can be
missing/None, especially for non-US tickers. Every filter fails safe:
missing data means the check does NOT pass, it never defaults to True.
"""
from typing import Optional, Dict, Any
import yfinance as yf

FILTERS = {
    "min_yield_pct": 3.0,
    "max_payout_ratio": 0.70,
    "max_debt_to_ebitda": 4.0,
    "max_beta": 1.0,
}


def _safe_get(info: dict, key: str) -> Optional[float]:
    value = info.get(key)
    return None if value is None else value


def evaluate_candidate(ticker: str) -> Dict[str, Any]:
    tk = yf.Ticker(ticker)
    info = tk.info

    raw_yield = _safe_get(info, "dividendYield")
    dividend_yield_pct = None
    if raw_yield is not None:
        # yfinance has changed this field's units across versions --
        # some releases return a fraction (0.045), others a percent (4.5).
        # Treat anything <= 1 as a fraction and normalize to percent.
        dividend_yield_pct = raw_yield if raw_yield > 1 else raw_yield * 100

    payout_ratio = _safe_get(info, "payoutRatio")
    beta = _safe_get(info, "beta")
    total_debt = _safe_get(info, "totalDebt")
    ebitda = _safe_get(info, "ebitda")
    free_cashflow = _safe_get(info, "freeCashflow")

    debt_to_ebitda = None
    if total_debt is not None and ebitda not in (None, 0):
        debt_to_ebitda = total_debt / ebitda

    checks = {
        "yield_ok": dividend_yield_pct is not None and dividend_yield_pct >= FILTERS["min_yield_pct"],
        "payout_ok": payout_ratio is not None and payout_ratio <= FILTERS["max_payout_ratio"],
        "beta_ok": beta is not None and beta <= FILTERS["max_beta"],
        "debt_ok": debt_to_ebitda is not None and debt_to_ebitda <= FILTERS["max_debt_to_ebitda"],
        "fcf_positive": free_cashflow is not None and free_cashflow > 0,
    }

    return {
        "ticker": ticker,
        "passed": all(checks.values()),
        "dividend_yield_pct": None if dividend_yield_pct is None else round(dividend_yield_pct, 2),
        "payout_ratio": payout_ratio,
        "beta": beta,
        "debt_to_ebitda": debt_to_ebitda,
        "checks": checks,
    }
