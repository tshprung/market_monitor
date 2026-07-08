import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from trigger_engine import TriggerState, evaluate_trigger, compute_drawdown_pct


def test_compute_drawdown_pct_basic():
    assert compute_drawdown_pct(90, 100) == pytest.approx(-10.0)


def test_compute_drawdown_pct_at_reference():
    assert compute_drawdown_pct(100, 100) == pytest.approx(0.0)


def test_zero_reference_raises():
    with pytest.raises(ValueError):
        compute_drawdown_pct(50, 0)


# --- drawdown_pct mode (resets_on_new_high=True) ---

def test_new_high_resets_state():
    state = TriggerState(reference_price=100, triggered_thresholds=[-8, -15])
    result = evaluate_trigger(
        current_price=105, state=state, thresholds=[-8, -15, -25, -35],
        tranche_pct=25, resets_on_new_high=True,
    )
    assert result["new_high"] is True
    assert result["updated_state"].reference_price == 105
    assert result["updated_state"].triggered_thresholds == []
    assert result["new_signals"] == []


def test_single_threshold_crossed():
    state = TriggerState(reference_price=100, triggered_thresholds=[])
    result = evaluate_trigger(
        current_price=91, state=state, thresholds=[-8, -15, -25, -35],
        tranche_pct=25, resets_on_new_high=True,
    )
    assert len(result["new_signals"]) == 1
    assert result["new_signals"][0]["threshold"] == -8


def test_multiple_thresholds_crossed_in_one_run():
    state = TriggerState(reference_price=100, triggered_thresholds=[])
    result = evaluate_trigger(
        current_price=70, state=state, thresholds=[-8, -15, -25, -35],  # -30%
        tranche_pct=25, resets_on_new_high=True,
    )
    triggered = [s["threshold"] for s in result["new_signals"]]
    assert triggered == [-8, -15, -25]


def test_already_triggered_not_repeated():
    state = TriggerState(reference_price=100, triggered_thresholds=[-8])
    result = evaluate_trigger(
        current_price=91, state=state, thresholds=[-8, -15, -25, -35],
        tranche_pct=25, resets_on_new_high=True,
    )
    assert result["new_signals"] == []


def test_exact_threshold_boundary_triggers():
    state = TriggerState(reference_price=100, triggered_thresholds=[])
    result = evaluate_trigger(
        current_price=92, state=state, thresholds=[-8, -15, -25, -35],  # exactly -8%
        tranche_pct=25, resets_on_new_high=True,
    )
    assert result["new_signals"][0]["threshold"] == -8


# --- price_target mode (resets_on_new_high=False) ---

def test_price_target_first_tranche_at_target():
    # BEZQ-style: target=428, thresholds=[0, -10, -20, -30]
    state = TriggerState(reference_price=428, triggered_thresholds=[])
    result = evaluate_trigger(
        current_price=428, state=state, thresholds=[0, -10, -20, -30],
        tranche_pct=25, resets_on_new_high=False,
    )
    assert result["new_high"] is False  # price_target mode never reports new_high
    assert len(result["new_signals"]) == 1
    assert result["new_signals"][0]["threshold"] == 0


def test_price_target_above_target_no_trigger():
    state = TriggerState(reference_price=428, triggered_thresholds=[])
    result = evaluate_trigger(
        current_price=450, state=state, thresholds=[0, -10, -20, -30],
        tranche_pct=25, resets_on_new_high=False,
    )
    assert result["new_signals"] == []
    # reference price must NOT move even though current_price > reference
    assert result["updated_state"].reference_price == 428


def test_price_target_does_not_reset_on_rally_above_target():
    # Already triggered tranche at 0%, price rallies back up, then dips
    # again -- should not re-trigger the same 0% threshold twice.
    state = TriggerState(reference_price=428, triggered_thresholds=[0])
    result = evaluate_trigger(
        current_price=440, state=state, thresholds=[0, -10, -20, -30],
        tranche_pct=25, resets_on_new_high=False,
    )
    assert result["new_signals"] == []
    assert result["updated_state"].triggered_thresholds == [0]


def test_price_target_deeper_drop_triggers_next_tranche():
    state = TriggerState(reference_price=428, triggered_thresholds=[0])
    result = evaluate_trigger(
        current_price=380, state=state, thresholds=[0, -10, -20, -30],  # ~-11.2% below 428
        tranche_pct=25, resets_on_new_high=False,
    )
    triggered = [s["threshold"] for s in result["new_signals"]]
    assert triggered == [-10]
