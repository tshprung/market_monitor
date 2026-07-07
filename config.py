"""Instrument universe, thresholds, and dividend watchlist.

Edit this file to add/remove tickers or change trigger sensitivity.
No other file needs to change for that kind of update.
"""

# Index signal tickers (used only to compute all-time-high / drawdown)
# and the actual UCITS/local vehicle you'd buy through your broker.
INDEX_INSTRUMENTS = {
    "S&P 500":    {"signal_ticker": "^GSPC",     "buy_ticker": "CSPX.UK",       "broker": "XTB"},
    "Nasdaq 100": {"signal_ticker": "^NDX",       "buy_ticker": "EQQQ.DE",       "broker": "XTB"},
    "DAX":        {"signal_ticker": "^GDAXI",     "buy_ticker": "EXS1.DE",       "broker": "XTB"},
    "FTSE 100":   {"signal_ticker": "^FTSE",      "buy_ticker": "VUKE.L",        "broker": "XTB"},
    "WIG20":      {"signal_ticker": "WIG20.WA",   "buy_ticker": "ETFBW20TR.WA",  "broker": "eMakler/XTB"},
    "TA-35":      {"signal_ticker": "^TA125.TA",  "buy_ticker": "TA-35 tracking fund", "broker": "Meitav Trade"},
}

# Buy this % of your planned allocation each time price falls this %
# below its rolling all-time high (within the fetched history window).
# A new all-time high resets the cycle so the same drop isn't bought twice.
DRAWDOWN_THRESHOLDS_PCT = [-8, -15, -25, -35]
TRANCHE_PCT = 25  # 4 equal tranches

# Dividend candidate universe across your brokers/markets.
# Extend any time -- the screener re-evaluates fresh live data each run.
DIVIDEND_WATCHLIST = {
    "XTB (US)":         ["HRL", "BEN", "O", "KVUE", "PEP", "JNJ", "KO", "PG", "AMCR"],
    "XTB (DE/UK)":      ["ALV.DE", "SIE.DE", "BAS.DE", "NG.L", "ULVR.L", "BATS.L"],
    "eMakler (PL)":     ["PZU.WA", "PKO.WA", "KGH.WA"],
    "Meitav Trade (IL)":["LUMI.TA", "BEZQ.TA"],
}

DIVIDEND_FILTERS = {
    "min_yield_pct": 3.0,
    "max_payout_ratio": 0.70,
    "max_debt_to_ebitda": 4.0,
    "max_beta": 1.0,
    "min_piotroski": 6,  # out of 9, best-effort -- see fundamentals.py
}

STATE_FILE = "state.json"
PRICE_HISTORY_PERIOD = "10y"  # approximation of all-time-high window
