"""Entry point: check price triggers (indices + qualifying dividend
stocks) and the dividend fundamental screener, send one consolidated
Telegram alert, persist state.json for next run.
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Tuple

from config import (
    INDEX_INSTRUMENTS,
    DIVIDEND_INSTRUMENTS,
    DIVIDEND_FILTERS,
    STATE_FILE,
    PRICE_HISTORY_PERIOD,
)
from trigger_engine import TriggerState, evaluate_trigger
from data_fetch import get_current_price_and_high, get_latest_price
from dividend_screener import evaluate_candidate
from fundamentals import compute_piotroski_score
from telegram_notify import send_telegram_message


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _fetch_current_and_reference(ticker: str, trigger: dict) -> Tuple[float, float]:
    """One generic entry point for both trigger types:
    - drawdown_pct: reference = rolling all-time high (needs full history)
    - price_target: reference = the fixed target already in config (only
      needs today's price, not years of history)
    """
    if trigger["type"] == "drawdown_pct":
        return get_current_price_and_high(ticker, period=PRICE_HISTORY_PERIOD)
    elif trigger["type"] == "price_target":
        current_price = get_latest_price(ticker)
        return current_price, trigger["target"]
    raise ValueError(f"Unknown trigger type: {trigger['type']}")


def check_trigger(name: str, ticker: str, trigger: dict, saved_state: dict) -> Tuple[List[str], dict]:
    """Generic check used for EVERY instrument, index or dividend stock.
    Returns (alert_messages, updated_state_entry)."""
    current_price, reference_price = _fetch_current_and_reference(ticker, trigger)

    if saved_state is None:
        tranche_state = TriggerState(reference_price=reference_price, triggered_thresholds=[])
    else:
        tranche_state = TriggerState(
            reference_price=saved_state["reference_price"],
            triggered_thresholds=list(saved_state["triggered_thresholds"]),
        )

    result = evaluate_trigger(
        current_price=current_price,
        state=tranche_state,
        thresholds=trigger["thresholds"],
        tranche_pct=trigger["tranche_pct"],
        resets_on_new_high=trigger["resets_on_new_high"],
    )

    messages = []
    if result["new_high"]:
        messages.append(f"\U0001F4C8 {name}: new high reached ({current_price:.2f}). Buy cycle reset.")
    for signal in result["new_signals"]:
        messages.append(
            f"\U0001F514 {name}: {signal['drawdown']:.1f}% vs. reference \u2192 "
            f"BUY {signal['tranche_pct']}% tranche ({ticker})"
        )

    updated = result["updated_state"]
    updated_entry = {
        "reference_price": updated.reference_price,
        "triggered_thresholds": updated.triggered_thresholds,
    }
    return messages, updated_entry


def check_indices(state: dict) -> List[str]:
    messages = []
    index_state = state.setdefault("indices", {})

    for name, meta in INDEX_INSTRUMENTS.items():
        try:
            msgs, updated_entry = check_trigger(
                name, meta["signal_ticker"], meta["trigger"], index_state.get(name)
            )
        except Exception as exc:
            messages.append(f"\u26a0\ufe0f {name}: data fetch failed ({exc})")
            continue

        # Buy-vehicle/broker context only matters for actionable signals.
        msgs = [
            f"{m} \u2014 buy via {meta['buy_ticker']} ({meta['broker']})" if "BUY" in m else m
            for m in msgs
        ]
        messages.extend(msgs)
        index_state[name] = updated_entry

    return messages


def check_dividends(state: dict) -> List[str]:
    messages = []
    dividend_state = state.setdefault("dividends", {})

    for ticker, meta in DIVIDEND_INSTRUMENTS.items():
        try:
            fundamentals_result = evaluate_candidate(ticker)
            score = compute_piotroski_score(ticker)
        except Exception as exc:
            messages.append(f"\u26a0\ufe0f {ticker}: screening failed ({exc})")
            continue

        piotroski_ok = score is not None and score >= DIVIDEND_FILTERS["min_piotroski"]
        passes_fundamentals = fundamentals_result["passed"] and piotroski_ok

        if not passes_fundamentals:
            continue  # don't time an entry into something failing on quality

        messages.append(
            f"\u2705 {ticker} ({meta['group']}): yield {fundamentals_result['dividend_yield_pct']}%, "
            f"payout {fundamentals_result['payout_ratio']}, beta {fundamentals_result['beta']}, "
            f"F-Score {score}/9 \u2014 passes all fundamental filters"
        )

        try:
            price_msgs, updated_entry = check_trigger(
                ticker, ticker, meta["trigger"], dividend_state.get(ticker)
            )
            messages.extend(price_msgs)
            dividend_state[ticker] = updated_entry
        except Exception as exc:
            messages.append(f"\u26a0\ufe0f {ticker}: price trigger check failed ({exc})")

    return messages


def main():
    state = load_state()
    index_messages = check_indices(state)
    dividend_messages = check_dividends(state)

    all_messages = index_messages + dividend_messages
    if all_messages:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        body = "\n".join(all_messages)
        send_telegram_message(f"\U0001F4CA Market monitor \u2014 {timestamp}\n\n{body}")
    else:
        print("No signals this run.")

    save_state(state)


if __name__ == "__main__":
    main()
