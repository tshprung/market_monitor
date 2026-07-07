import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import fundamentals


class FakeTicker:
    def __init__(self, financials, balance_sheet, cashflow):
        self.financials = financials
        self.balance_sheet = balance_sheet
        self.cashflow = cashflow


def _df(rows: dict, cols=("2025", "2024")):
    return pd.DataFrame(rows, index=cols).T


def test_insufficient_columns_returns_none(monkeypatch):
    # Only one year of data -> can't do YoY checks
    financials = _df({"Net Income": [100]}, cols=("2025",))
    balance = _df({"Total Assets": [1000]}, cols=("2025",))
    cashflow = _df({"Operating Cash Flow": [120]}, cols=("2025",))
    monkeypatch.setattr(
        fundamentals.yf, "Ticker",
        lambda t: FakeTicker(financials, balance, cashflow),
    )
    assert fundamentals.compute_piotroski_score("FAKE") is None


def test_strong_company_scores_high(monkeypatch):
    financials = _df({
        "Net Income": [150, 100],
        "Gross Profit": [400, 300],
        "Total Revenue": [1000, 900],
    })
    balance = _df({
        "Total Assets": [2000, 1900],
        "Long Term Debt": [300, 400],
        "Current Assets": [800, 700],
        "Current Liabilities": [400, 400],
        "Share Issued": [100, 100],
    })
    cashflow = _df({"Operating Cash Flow": [200, 150]})

    monkeypatch.setattr(
        fundamentals.yf, "Ticker",
        lambda t: FakeTicker(financials, balance, cashflow),
    )
    score = fundamentals.compute_piotroski_score("FAKE")
    assert score is not None
    # All 9 sub-checks should favor this improving company
    assert score == 9


def test_weak_company_scores_low(monkeypatch):
    financials = _df({
        "Net Income": [-50, 100],
        "Gross Profit": [200, 300],
        "Total Revenue": [1000, 900],
    })
    balance = _df({
        "Total Assets": [2000, 1900],
        "Long Term Debt": [500, 400],
        "Current Assets": [400, 700],
        "Current Liabilities": [500, 400],
        "Share Issued": [110, 100],
    })
    cashflow = _df({"Operating Cash Flow": [-20, 150]})

    monkeypatch.setattr(
        fundamentals.yf, "Ticker",
        lambda t: FakeTicker(financials, balance, cashflow),
    )
    score = fundamentals.compute_piotroski_score("FAKE")
    assert score is not None
    assert score <= 3


def test_missing_statement_returns_none(monkeypatch):
    monkeypatch.setattr(
        fundamentals.yf, "Ticker",
        lambda t: FakeTicker(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
    )
    assert fundamentals.compute_piotroski_score("FAKE") is None
