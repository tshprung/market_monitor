"""Historical backtest for the tranche-buying rules.

This is deliberately separate from the live monitor. It answers two questions:
1. After a drawdown threshold is reached, what happened over the next 3/6/12/24 months?
2. How did different tranche allocations deploy a fixed cash reserve?

Usage:
    python backtest.py

The simulation uses daily closes and a peak that is known only up to each
trading day, so it does not use future prices to define a historical signal.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd
import yfinance as yf


STRATEGIES = {
    "current_25_each": ([-8, -15, -25, -35], [25, 25, 25, 25]),
    "backloaded": ([-8, -15, -25, -35], [10, 20, 30, 40]),
    "more_conservative_start": ([-10, -15, -25, -35], [10, 20, 30, 40]),
}

TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "DAX": "^GDAXI",
    "FTSE 100": "^FTSE",
    "WIG20": "WIG20.WA",
    "TA-35": "^TA125.TA",
}

FORWARD_DAYS = {
    "3m": 63,
    "6m": 126,
    "12m": 252,
    "24m": 504,
}


@dataclass
class Signal:
    date: pd.Timestamp
    threshold: float
    price: float
    drawdown: float


def load_prices(ticker: str, period: str = "max") -> pd.Series:
    data = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")
    prices = data["Close"].dropna()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return prices


def find_signals(prices: pd.Series, thresholds: List[float]) -> List[Signal]:
    """Replicate the live drawdown engine using only information available that day."""
    reference = None
    triggered: List[float] = []
    signals: List[Signal] = []

    for date, price in prices.items():
        price = float(price)
        if reference is None or price > reference:
            reference = price
            triggered = []
            continue

        drawdown = (price / reference - 1.0) * 100.0
        for threshold in thresholds:
            if drawdown <= threshold and threshold not in triggered:
                signals.append(Signal(date, threshold, price, drawdown))
                triggered.append(threshold)

    return signals


def forward_return(prices: pd.Series, date: pd.Timestamp, days: int):
    try:
        start_pos = prices.index.get_loc(date)
    except KeyError:
        return None
    end_pos = start_pos + days
    if end_pos >= len(prices):
        return None
    return float(prices.iloc[end_pos] / prices.iloc[start_pos] - 1.0) * 100.0


def event_study(prices: pd.Series, signals: List[Signal]) -> pd.DataFrame:
    rows = []
    for signal in signals:
        row = {
            "date": signal.date.date().isoformat(),
            "threshold": signal.threshold,
            "price": round(signal.price, 2),
            "drawdown": round(signal.drawdown, 2),
        }
        for label, days in FORWARD_DAYS.items():
            row[f"forward_{label}"] = forward_return(prices, signal.date, days)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_event_study(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()

    rows = []
    for threshold, group in events.groupby("threshold"):
        row = {
            "threshold": threshold,
            "signals": len(group),
        }
        for label in FORWARD_DAYS:
            values = group[f"forward_{label}"].dropna()
            row[f"{label}_avg"] = round(values.mean(), 2) if len(values) else None
            row[f"{label}_median"] = round(values.median(), 2) if len(values) else None
            row[f"{label}_positive_pct"] = round((values > 0).mean() * 100, 1) if len(values) else None
        rows.append(row)
    return pd.DataFrame(rows)


def simulate(prices: pd.Series, thresholds: List[float], allocations: List[float]) -> Dict[str, float]:
    """Deploy a 100-unit cash reserve according to the live trigger semantics."""
    if abs(sum(allocations) - 100) > 1e-9:
        raise ValueError("allocations must sum to 100")

    reference = None
    triggered: List[float] = []
    cash = 100.0
    shares = 0.0
    buys = 0

    allocation_by_threshold = dict(zip(thresholds, allocations))

    for _, price in prices.items():
        price = float(price)
        if reference is None or price > reference:
            reference = price
            triggered = []
            continue

        drawdown = (price / reference - 1.0) * 100.0
        for threshold in thresholds:
            if drawdown <= threshold and threshold not in triggered:
                amount = allocation_by_threshold[threshold]
                if cash > 0:
                    amount = min(amount, cash)
                    shares += amount / price
                    cash -= amount
                    buys += 1
                triggered.append(threshold)

    final_value = cash + shares * float(prices.iloc[-1])
    return {
        "final_value": final_value,
        "cash_remaining": cash,
        "deployed": 100.0 - cash,
        "buys": buys,
    }


def run_one(name: str, ticker: str):
    prices = load_prices(ticker)
    print(f"\n=== {name} ({ticker}) | {prices.index[0].date()} -> {prices.index[-1].date()} ===")

    for strategy_name, (thresholds, allocations) in STRATEGIES.items():
        signals = find_signals(prices, thresholds)
        events = event_study(prices, signals)
        summary = summarize_event_study(events)
        sim = simulate(prices, thresholds, allocations)

        print(f"\n{strategy_name}: thresholds={thresholds}, allocations={allocations}")
        print(f"signals={len(signals)}, deployed={sim['deployed']:.1f}, final_value={sim['final_value']:.2f}, buys={sim['buys']}")
        if not summary.empty:
            print(summary.to_string(index=False))


if __name__ == "__main__":
    for name, ticker in TICKERS.items():
        try:
            run_one(name, ticker)
        except Exception as exc:
            print(f"\n{name}: FAILED ({exc})")
