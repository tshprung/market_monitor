"""Generic price-trigger logic for tranche-based buying.

One evaluation function drives two interchangeable trigger types --
which type is used is a per-instrument config choice, not different code:

  - "drawdown_pct": reference price is the rolling all-time high.
    A new high updates the reference and resets triggered tranches.
    (resets_on_new_high=True)

  - "price_target": reference price is a fixed value you choose.
    It never moves, so tranches accumulate downward from that fixed
    point and are never reset by a price rally above it.
    (resets_on_new_high=False)

No I/O here -- fully unit-testable with plain floats.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TriggerState:
    reference_price: float
    triggered_thresholds: List[float] = field(default_factory=list)


def compute_drawdown_pct(current_price: float, reference_price: float) -> float:
    """Returns % below reference_price (-8.0 means -8% below it)."""
    if reference_price <= 0:
        raise ValueError("reference_price must be positive")
    return (current_price / reference_price - 1.0) * 100.0


def evaluate_trigger(
    current_price: float,
    state: TriggerState,
    thresholds: List[float],
    tranche_pct: float,
    resets_on_new_high: bool,
) -> Dict[str, Any]:
    """
    A single call can fire multiple thresholds at once (a sharp drop
    that skips past an earlier tranche point still buys it).

    Returns: {"new_high": bool, "new_signals": [dict, ...], "updated_state": TriggerState}
    """
    if resets_on_new_high and current_price > state.reference_price:
        new_state = TriggerState(reference_price=current_price, triggered_thresholds=[])
        return {"new_high": True, "new_signals": [], "updated_state": new_state}

    drawdown = compute_drawdown_pct(current_price, state.reference_price)
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

    updated_state = TriggerState(
        reference_price=state.reference_price,
        triggered_thresholds=triggered_now,
    )
    return {"new_high": False, "new_signals": new_signals, "updated_state": updated_state}
