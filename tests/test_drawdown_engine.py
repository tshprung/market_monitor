import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from drawdown_engine import TrancheState, evaluate_signal, compute_drawdown_pct


def test_compute_drawdown_pct_basic():
    assert compute_drawdown_pct(90, 100) == pytest.approx(-10.0)


def test_compute_drawdown_pct_at_high():
    assert compute_drawdown_pct(100, 100) == 0.0


def test_new_high_resets_state():
    state = TrancheState(all_time_high=100, triggered_thresholds=[-8, -15])
    result = evaluate_signal(
        current_price=105, historical_high=100, state=state,
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    assert result["new_high"] is True
    assert result["updated_state"].all_time_high == 105
    assert result["updated_state"].triggered_thresholds == []
    assert result["new_signals"] == []


def test_single_threshold_crossed():
    state = TrancheState(all_time_high=100, triggered_thresholds=[])
    result = evaluate_signal(
        current_price=91, historical_high=100, state=state,
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    assert result["new_high"] is False
    assert len(result["new_signals"]) == 1
    assert result["new_signals"][0]["threshold"] == -8
    assert -8 in result["updated_state"].triggered_thresholds


def test_multiple_thresholds_crossed_in_one_run():
    state = TrancheState(all_time_high=100, triggered_thresholds=[])
    result = evaluate_signal(
        current_price=70, historical_high=100, state=state,  # -30%
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    triggered = [s["threshold"] for s in result["new_signals"]]
    assert triggered == [-8, -15, -25]
    assert -35 not in result["updated_state"].triggered_thresholds


def test_already_triggered_threshold_not_repeated():
    state = TrancheState(all_time_high=100, triggered_thresholds=[-8])
    result = evaluate_signal(
        current_price=91, historical_high=100, state=state,  # still -9%
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    assert result["new_signals"] == []


def test_deeper_drop_after_partial_trigger():
    state = TrancheState(all_time_high=100, triggered_thresholds=[-8])
    result = evaluate_signal(
        current_price=84, historical_high=100, state=state,  # -16%
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    triggered = [s["threshold"] for s in result["new_signals"]]
    assert triggered == [-15]


def test_exact_threshold_boundary_triggers():
    state = TrancheState(all_time_high=100, triggered_thresholds=[])
    result = evaluate_signal(
        current_price=92, historical_high=100, state=state,  # exactly -8%
        thresholds=[-8, -15, -25, -35], tranche_pct=25,
    )
    assert result["new_signals"][0]["threshold"] == -8


def test_zero_all_time_high_raises():
    import pytest
    with pytest.raises(ValueError):
        compute_drawdown_pct(50, 0)
