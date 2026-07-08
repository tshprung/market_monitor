"""Instrument universe, trigger rules, and dividend fundamental filters.

Every instrument (index or dividend stock) gets a "trigger" config that
the SAME generic engine (trigger_engine.py) evaluates. There is no
per-ticker special-cased code anywhere -- only per-ticker DATA:

  - type "drawdown_pct": buy tranches as price falls below its rolling
    all-time high. thresholds are % below that high.
  - type "price_target": buy tranches below a fixed price you choose.
    thresholds are % below that fixed price (0 = at/below the target
    itself, -10 = 10% further below it, etc).

Edit this file to add/remove tickers or change trigger sensitivity.
No other file needs to change for that kind of update.
"""


def drawdown_trigger(thresholds=None, tranche_pct=25):
    """Default trigger: tranches below the instrument's own rolling high."""
    return {
        "type": "drawdown_pct",
        "thresholds": list(thresholds) if thresholds else [-8, -15, -25, -35],
        "tranche_pct": tranche_pct,
        "resets_on_new_high": True,
    }


def price_target_trigger(target, drop_steps=None, tranche_pct=25):
    """Trigger anchored to a fixed price instead of a rolling high.
    drop_steps are % below `target` for each further tranche; include 0
    to buy the first tranche once price reaches the target itself."""
    return {
        "type": "price_target",
        "target": target,
        "thresholds": list(drop_steps) if drop_steps else [0, -10, -20, -30],
        "tranche_pct": tranche_pct,
        "resets_on_new_high": False,
    }


# Index signal tickers (used to compute the rolling all-time-high) and
# the actual UCITS/local vehicle you'd buy through your broker.
INDEX_INSTRUMENTS = {
    "S&P 500":    {"signal_ticker": "^GSPC",    "buy_ticker": "CSPX.UK",      "broker": "XTB",
                   "trigger": drawdown_trigger()},
    "Nasdaq 100": {"signal_ticker": "^NDX",      "buy_ticker": "EQQQ.DE",      "broker": "XTB",
                   "trigger": drawdown_trigger()},
    "DAX":        {"signal_ticker": "^GDAXI",    "buy_ticker": "EXS1.DE",      "broker": "XTB",
                   "trigger": drawdown_trigger()},
    "FTSE 100":   {"signal_ticker": "^FTSE",     "buy_ticker": "VUKE.L",       "broker": "XTB",
                   "trigger": drawdown_trigger()},
    "WIG20":      {"signal_ticker": "WIG20.WA",  "buy_ticker": "ETFBW20TR.WA", "broker": "eMakler/XTB",
                   "trigger": drawdown_trigger()},
    # Wider thresholds: TA-35 rallied ~52% in 2025 and hit new highs into
    # mid-2026 before a June correction -- the standard -8% first tranche
    # would fire almost immediately after a move like that. Feed me more
    # feedback here as you watch how the correction develops.
    "TA-35":      {"signal_ticker": "^TA125.TA", "buy_ticker": "TA-35 tracking fund", "broker": "Meitav Trade",
                   "trigger": drawdown_trigger(thresholds=[-15, -25, -35, -45])},
}

# Dividend candidate universe. Each ticker has a "group" (broker/market)
# and a "trigger". Price triggers are only checked for tickers that are
# ALSO currently passing the fundamental filters below (see main.py) --
# no point timing an entry into something that fails on quality.
DIVIDEND_INSTRUMENTS = {
    "HRL":     {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "BEN":     {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "O":       {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "KVUE":    {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "PEP":     {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "JNJ":     {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "KO":      {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "PG":      {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "AMCR":    {"group": "XTB (US)",          "trigger": drawdown_trigger()},
    "ALV.DE":  {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "SIE.DE":  {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "BAS.DE":  {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "NG.L":    {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "ULVR.L":  {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "BATS.L":  {"group": "XTB (DE/UK)",       "trigger": drawdown_trigger()},
    "PZU.WA":  {"group": "eMakler (PL)",      "trigger": drawdown_trigger()},
    "PKO.WA":  {"group": "eMakler (PL)",      "trigger": drawdown_trigger()},
    "KGH.WA":  {"group": "eMakler (PL)",      "trigger": drawdown_trigger()},
    "LUMI.TA": {"group": "Meitav Trade (IL)", "trigger": drawdown_trigger()},
    # Anchored to your mid-2024 reference point instead of a rolling high.
    # thresholds=[0,-10,-20,-30] -> first tranche at/below 428, then
    # further tranches at 10/20/30% below that. Adjust the split any time.
    "BEZQ.TA": {"group": "Meitav Trade (IL)",
                "trigger": price_target_trigger(target=428, drop_steps=[0, -10, -20, -30])},
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
