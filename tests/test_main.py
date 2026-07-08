import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as main_module


def test_check_trigger_multiple_tranches_have_distinct_messages(monkeypatch):
    # A sharp drop past several thresholds at once must produce messages
    # that are distinguishable from each other, not identical duplicates.
    monkeypatch.setattr(
        main_module, "get_current_price_and_high", lambda ticker, period: (70.0, 100.0)  # -30%
    )
    trigger = {
        "type": "drawdown_pct", "thresholds": [-8, -15, -25, -35],
        "tranche_pct": 25, "resets_on_new_high": True,
    }
    messages, _ = main_module.check_trigger("TEST", "TEST.X", trigger, None)
    assert len(messages) == 3  # -8, -15, -25 all fire; -35 does not
    assert len(set(messages)) == 3  # all distinct, not copies of each other
    assert any("-8%" in m for m in messages)
    assert any("-15%" in m for m in messages)
    assert any("-25%" in m for m in messages)


def test_check_trigger_first_run_seeds_state_from_fetch(monkeypatch):
    # drawdown_pct: first run (saved_state=None) must seed reference_price
    # from the fetched historical high, not from today's price.
    monkeypatch.setattr(
        main_module, "get_current_price_and_high", lambda ticker, period: (85.0, 100.0)
    )
    trigger = {
        "type": "drawdown_pct", "thresholds": [-8, -15, -25, -35],
        "tranche_pct": 25, "resets_on_new_high": True,
    }
    messages, updated_entry = main_module.check_trigger("TEST", "TEST.X", trigger, None)
    assert updated_entry["reference_price"] == 100.0
    assert any("BUY" in m for m in messages)  # -15% below 100 should fire -8% tranche


def test_check_trigger_state_round_trip(monkeypatch):
    # Second run must read back exactly what was saved, not re-derive it.
    monkeypatch.setattr(
        main_module, "get_current_price_and_high", lambda ticker, period: (91.0, 100.0)
    )
    trigger = {
        "type": "drawdown_pct", "thresholds": [-8, -15, -25, -35],
        "tranche_pct": 25, "resets_on_new_high": True,
    }
    saved_state = {"reference_price": 100.0, "triggered_thresholds": [-8]}
    messages, updated_entry = main_module.check_trigger("TEST", "TEST.X", trigger, saved_state)
    # -9% is still only past -8, which was already triggered -> no new signal
    assert messages == []
    assert updated_entry["triggered_thresholds"] == [-8]


def test_check_trigger_price_target_uses_latest_price_only(monkeypatch):
    # price_target mode must call get_latest_price, NOT the full-history fetch.
    def fail_if_called(*args, **kwargs):
        raise AssertionError("get_current_price_and_high should not be called for price_target")

    monkeypatch.setattr(main_module, "get_current_price_and_high", fail_if_called)
    monkeypatch.setattr(main_module, "get_latest_price", lambda ticker: 400.0)

    trigger = {
        "type": "price_target", "target": 428, "thresholds": [0, -10, -20, -30],
        "tranche_pct": 25, "resets_on_new_high": False,
    }
    messages, updated_entry = main_module.check_trigger("BEZQ.TA", "BEZQ.TA", trigger, None)
    assert updated_entry["reference_price"] == 428
    assert any("BUY" in m for m in messages)


def test_check_dividends_skips_price_check_when_fundamentals_fail(monkeypatch):
    monkeypatch.setattr(
        main_module, "DIVIDEND_INSTRUMENTS",
        {"FAIL": {"group": "test", "trigger": {
            "type": "drawdown_pct", "thresholds": [-8, -15, -25, -35],
            "tranche_pct": 25, "resets_on_new_high": True,
        }}},
    )
    monkeypatch.setattr(
        main_module, "evaluate_candidate",
        lambda ticker: {"passed": False, "dividend_yield_pct": 1.0, "payout_ratio": 0.9, "beta": 2.0},
    )
    monkeypatch.setattr(main_module, "compute_piotroski_score", lambda ticker: 2)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("check_trigger should not run for a ticker failing fundamentals")

    monkeypatch.setattr(main_module, "check_trigger", fail_if_called)

    state = {}
    messages = main_module.check_dividends(state)
    assert messages == []  # no crash, no price check attempted, no message


def test_check_dividends_runs_price_check_when_fundamentals_pass(monkeypatch):
    monkeypatch.setattr(
        main_module, "DIVIDEND_INSTRUMENTS",
        {"PASS": {"group": "test", "trigger": {
            "type": "drawdown_pct", "thresholds": [-8, -15, -25, -35],
            "tranche_pct": 25, "resets_on_new_high": True,
        }}},
    )
    monkeypatch.setattr(
        main_module, "evaluate_candidate",
        lambda ticker: {"passed": True, "dividend_yield_pct": 5.0, "payout_ratio": 0.5, "beta": 0.5},
    )
    monkeypatch.setattr(main_module, "compute_piotroski_score", lambda ticker: 7)
    monkeypatch.setattr(
        main_module, "check_trigger",
        lambda name, ticker, trigger, saved_state: (["price msg"], {"reference_price": 1, "triggered_thresholds": []}),
    )

    state = {}
    messages = main_module.check_dividends(state)
    assert "price msg" in messages
    assert any("passes all fundamental filters" in m for m in messages)
    assert state["dividends"]["PASS"]["reference_price"] == 1
