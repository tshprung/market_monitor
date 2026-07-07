"""Pure logic for computing drawdown-based buy signals.

Deliberately has zero I/O so it can be unit-tested without hitting
the network or touching pandas/yfinance objects directly.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TrancheState:
    all_time_high: float
    triggered_thresholds: List[float] = field(default_factory=list)


def compute_drawdown_pct(current_price: float, all_time_high: float) -> float:
    """Returns drawdown as a negative percentage (-8.0 means -8%)."""
    if all_time_high <= 0:
        raise ValueError("all_time_high must be positive")
    return (current_price / all_time_high - 1.0) * 100.0


def evaluate_signal(
    current_price: float,
    historical_high: float,
    state: TrancheState,
    thresholds: List[float],
    tranche_pct: float,
) -> Dict[str, Any]:
    """
    Decide whether a new all-time high resets the tranche cycle, and
    whether any new threshold has been crossed since the last check.

    thresholds: e.g. [-8, -15, -25, -35], least-severe first.
    A single call can trigger several thresholds at once (a sharp drop
    that skips past an earlier tranche point still buys it).

    Returns: {"new_high": bool, "new_signals": [dict, ...], "updated_state": TrancheState}
    """
    if current_price > state.all_time_high:
        new_state = TrancheState(all_time_high=current_price, triggered_thresholds=[])
        return {"new_high": True, "new_signals": [], "updated_state": new_state}

    drawdown = compute_drawdown_pct(current_price, state.all_time_high)
    triggered_now = list(state.triggered_thresholds)
    new_signals = []
    epsilon = 1e-9  # guards against float rounding at exact threshold boundaries

    for threshold in thresholds:
        if drawdown <= threshold + epsilon and threshold not in triggered_now:
            new_signals.append({
                "threshold": threshold,
                "tranche_pct": tranche_pct,
                "drawdown": drawdown,
            })
            triggered_now.append(threshold)

    updated_state = TrancheState(
        all_time_high=state.all_time_high,
        triggered_thresholds=triggered_now,
    )
    return {"new_high": False, "new_signals": new_signals, "updated_state": updated_state}
