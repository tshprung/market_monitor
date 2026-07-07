"""Wraps yfinance calls for index/ETF price history.

All pandas scalar extraction goes through .item() to avoid the
FutureWarning/deprecation noise from implicit Series-to-float casts
in recent pandas versions.
"""
from typing import Tuple
import pandas as pd
import yfinance as yf


def get_price_history(ticker: str, period: str = "10y") -> pd.DataFrame:
    data = yf.Ticker(ticker).history(period=period, interval="1d")
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")
    return data


def get_current_price_and_high(ticker: str, period: str = "10y") -> Tuple[float, float]:
    """Returns (latest_close, highest_close_in_period) as plain floats.

    Note: 'all-time high' here is bounded by `period`. 10y is a practical
    proxy -- true all-time-high data isn't reliably free for all 6 markets.
    """
    data = get_price_history(ticker, period=period)
    current_price = data["Close"].iloc[-1].item()
    all_time_high = data["Close"].cummax().iloc[-1].item()
    return current_price, all_time_high
