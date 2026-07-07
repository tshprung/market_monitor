"""Best-effort Piotroski F-Score (0-9) from yfinance annual statements.

Requires two annual periods of data for each statement; returns None
if that's not available (common for smaller-cap or non-US tickers --
yfinance's statement coverage outside the US is inconsistent).

Caveat: a handful of the 9 sub-checks are skipped (not counted either
way) if a specific line item is missing, so the score is conservative
but not strictly comparable to a textbook Piotroski score computed from
complete data. Good enough as a relative quality filter across your
watchlist, not a precise external benchmark.
"""
from typing import Optional
import pandas as pd
import yfinance as yf


def _row_value(df: pd.DataFrame, row_name: str, col_idx: int) -> Optional[float]:
    if df is None or df.empty or row_name not in df.index:
        return None
    series = df.loc[row_name]
    if col_idx >= len(series):
        return None
    value = series.iloc[col_idx]
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else float(value)


def compute_piotroski_score(ticker: str) -> Optional[int]:
    tk = yf.Ticker(ticker)
    income = tk.financials
    balance = tk.balance_sheet
    cashflow = tk.cashflow

    if income.empty or balance.empty or cashflow.empty:
        return None
    if income.shape[1] < 2 or balance.shape[1] < 2 or cashflow.shape[1] < 2:
        return None  # need 2 years for every year-over-year check

    net_income_t = _row_value(income, "Net Income", 0)
    net_income_t1 = _row_value(income, "Net Income", 1)
    total_assets_t = _row_value(balance, "Total Assets", 0)
    total_assets_t1 = _row_value(balance, "Total Assets", 1)
    op_cf_t = _row_value(cashflow, "Operating Cash Flow", 0)

    required = [net_income_t, net_income_t1, total_assets_t, total_assets_t1, op_cf_t]
    if any(v is None for v in required) or total_assets_t == 0 or total_assets_t1 == 0:
        return None  # not enough core data for a meaningful score

    roa_t = net_income_t / total_assets_t
    roa_t1 = net_income_t1 / total_assets_t1

    score = 0
    score += 1 if net_income_t > 0 else 0
    score += 1 if op_cf_t > 0 else 0
    score += 1 if roa_t > roa_t1 else 0
    score += 1 if op_cf_t > net_income_t else 0

    lt_debt_t = _row_value(balance, "Long Term Debt", 0)
    lt_debt_t1 = _row_value(balance, "Long Term Debt", 1)
    if lt_debt_t is not None and lt_debt_t1 is not None:
        score += 1 if (lt_debt_t / total_assets_t) < (lt_debt_t1 / total_assets_t1) else 0

    current_assets_t = _row_value(balance, "Current Assets", 0)
    current_liab_t = _row_value(balance, "Current Liabilities", 0)
    current_assets_t1 = _row_value(balance, "Current Assets", 1)
    current_liab_t1 = _row_value(balance, "Current Liabilities", 1)
    if None not in (current_assets_t, current_liab_t, current_assets_t1, current_liab_t1) and current_liab_t and current_liab_t1:
        current_ratio_t = current_assets_t / current_liab_t
        current_ratio_t1 = current_assets_t1 / current_liab_t1
        score += 1 if current_ratio_t > current_ratio_t1 else 0

    shares_t = _row_value(balance, "Share Issued", 0)
    shares_t1 = _row_value(balance, "Share Issued", 1)
    if shares_t is not None and shares_t1 is not None:
        score += 1 if shares_t <= shares_t1 else 0

    gross_profit_t = _row_value(income, "Gross Profit", 0)
    revenue_t = _row_value(income, "Total Revenue", 0)
    gross_profit_t1 = _row_value(income, "Gross Profit", 1)
    revenue_t1 = _row_value(income, "Total Revenue", 1)
    if None not in (gross_profit_t, revenue_t, gross_profit_t1, revenue_t1) and revenue_t and revenue_t1:
        margin_t = gross_profit_t / revenue_t
        margin_t1 = gross_profit_t1 / revenue_t1
        score += 1 if margin_t > margin_t1 else 0

        turnover_t = revenue_t / total_assets_t
        turnover_t1 = revenue_t1 / total_assets_t1
        score += 1 if turnover_t > turnover_t1 else 0

    return score
