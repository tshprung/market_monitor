"""Entry point: check index drawdown tranches + dividend screener,
send one consolidated Telegram alert, persist state.json for next run.
"""
import json
import os
from datetime import datetime, timezone
from typing import List

from config import (
    INDEX_INSTRUMENTS,
    DRAWDOWN_THRESHOLDS_PCT,
    TRANCHE_PCT,
    DIVIDEND_WATCHLIST,
    DIVIDEND_FILTERS,
    STATE_FILE,
    PRICE_HISTORY_PERIOD,
)
from drawdown_engine import TrancheState, evaluate_signal
from data_fetch import get_current_price_and_high
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


def check_indices(state: dict) -> List[str]:
    messages = []
    index_state = state.setdefault("indices", {})

    for name, meta in INDEX_INSTRUMENTS.items():
        try:
            current_price, all_time_high = get_current_price_and_high(
                meta["signal_ticker"], period=PRICE_HISTORY_PERIOD
            )
        except Exception as exc:
            messages.append(f"\u26a0\ufe0f {name}: data fetch failed ({exc})")
            continue

        saved = index_state.get(name)
        if saved is None:
            tranche_state = TrancheState(all_time_high=all_time_high, triggered_thresholds=[])
        else:
            tranche_state = TrancheState(
                all_time_high=saved["all_time_high"],
                triggered_thresholds=list(saved["triggered_thresholds"]),
            )

        result = evaluate_signal(
            current_price=current_price,
            historical_high=all_time_high,
            state=tranche_state,
            thresholds=DRAWDOWN_THRESHOLDS_PCT,
            tranche_pct=TRANCHE_PCT,
        )

        if result["new_high"]:
            messages.append(f"\U0001F4C8 {name}: new high reached ({current_price:.2f}). Buy cycle reset.")
        for signal in result["new_signals"]:
            messages.append(
                f"\U0001F514 {name}: {signal['drawdown']:.1f}% below high \u2192 "
                f"BUY {signal['tranche_pct']}% tranche "
                f"({meta['buy_ticker']} via {meta['broker']})"
            )

        updated = result["updated_state"]
        index_state[name] = {
            "all_time_high": updated.all_time_high,
            "triggered_thresholds": updated.triggered_thresholds,
        }

    return messages


def check_dividends() -> List[str]:
    messages = []
    for group, tickers in DIVIDEND_WATCHLIST.items():
        for ticker in tickers:
            try:
                result = evaluate_candidate(ticker)
                score = compute_piotroski_score(ticker)
            except Exception as exc:
                messages.append(f"\u26a0\ufe0f {ticker}: screening failed ({exc})")
                continue

            piotroski_ok = score is not None and score >= DIVIDEND_FILTERS["min_piotroski"]
            if result["passed"] and piotroski_ok:
                messages.append(
                    f"\u2705 {ticker} ({group}): yield {result['dividend_yield_pct']}%, "
                    f"payout {result['payout_ratio']}, beta {result['beta']}, "
                    f"F-Score {score}/9 \u2014 passes all filters"
                )
    return messages


def main():
    state = load_state()
    index_messages = check_indices(state)
    dividend_messages = check_dividends()

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
