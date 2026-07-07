import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import dividend_screener


class FakeTicker:
    def __init__(self, info):
        self.info = info


def test_yield_normalization_fraction_form(monkeypatch):
    # Old yfinance style: dividendYield as a fraction (0.045 = 4.5%)
    info = {
        "dividendYield": 0.045,
        "payoutRatio": 0.5,
        "beta": 0.8,
        "totalDebt": 100,
        "ebitda": 50,
        "freeCashflow": 10,
    }
    monkeypatch.setattr(dividend_screener.yf, "Ticker", lambda t: FakeTicker(info))
    result = dividend_screener.evaluate_candidate("FAKE")
    assert result["dividend_yield_pct"] == 4.5


def test_yield_normalization_percent_form(monkeypatch):
    # Newer yfinance style: dividendYield already as percent (4.5 = 4.5%)
    info = {
        "dividendYield": 4.5,
        "payoutRatio": 0.5,
        "beta": 0.8,
        "totalDebt": 100,
        "ebitda": 50,
        "freeCashflow": 10,
    }
    monkeypatch.setattr(dividend_screener.yf, "Ticker", lambda t: FakeTicker(info))
    result = dividend_screener.evaluate_candidate("FAKE")
    assert result["dividend_yield_pct"] == 4.5


def test_missing_field_fails_safe(monkeypatch):
    # No beta at all -> beta_ok must be False, never default-True
    info = {
        "dividendYield": 4.5,
        "payoutRatio": 0.5,
        "beta": None,
        "totalDebt": 100,
        "ebitda": 50,
        "freeCashflow": 10,
    }
    monkeypatch.setattr(dividend_screener.yf, "Ticker", lambda t: FakeTicker(info))
    result = dividend_screener.evaluate_candidate("FAKE")
    assert result["checks"]["beta_ok"] is False
    assert result["passed"] is False


def test_all_filters_pass(monkeypatch):
    info = {
        "dividendYield": 5.0,
        "payoutRatio": 0.6,
        "beta": 0.7,
        "totalDebt": 200,
        "ebitda": 100,   # debt/ebitda = 2.0, under max 4.0
        "freeCashflow": 50,
    }
    monkeypatch.setattr(dividend_screener.yf, "Ticker", lambda t: FakeTicker(info))
    result = dividend_screener.evaluate_candidate("FAKE")
    assert result["passed"] is True


def test_debt_to_ebitda_over_limit_fails(monkeypatch):
    info = {
        "dividendYield": 5.0,
        "payoutRatio": 0.6,
        "beta": 0.7,
        "totalDebt": 1000,
        "ebitda": 100,   # debt/ebitda = 10.0, over max 4.0
        "freeCashflow": 50,
    }
    monkeypatch.setattr(dividend_screener.yf, "Ticker", lambda t: FakeTicker(info))
    result = dividend_screener.evaluate_candidate("FAKE")
    assert result["checks"]["debt_ok"] is False
    assert result["passed"] is False
