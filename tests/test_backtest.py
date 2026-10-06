import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace

import backtest


def prices(values):
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq="D"))


def test_drawdown_uses_running_high():
    actual = backtest.drawdowns(prices([100, 110, 99, 88]))
    assert actual.tolist() == pytest.approx([0, 0, -0.1, -0.2])


def test_expanding_percentile_excludes_current_observation():
    values = pd.Series([0.0, -0.1, -0.2, -0.05])
    result = backtest.expanding_severity_percentile(values, min_periods=2)
    assert np.isnan(result.iloc[0]) and np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(100.0)
    assert result.iloc[3] == pytest.approx(100 / 3)


def test_ladder_deploys_once_per_rung_and_resets_at_new_high():
    series = prices([100, 89, 79, 101, 90, 80, 70])
    orders = backtest.drawdown_orders(series, (-.1, -.2), (25, 25))
    assert [(o.position, o.amount) for o in orders] == [(2, 25), (3, 25), (5, 25), (6, 25)]


def test_ladder_crossing_multiple_rungs_executes_next_close():
    series = prices([100, 70, 80])
    orders = backtest.drawdown_orders(series, (-.1, -.2, -.3), (10, 10, 10))
    assert [(o.position, o.amount) for o in orders] == [(2, 10), (2, 10), (2, 10)]


def test_dca_equal_monthly_installments():
    series = pd.Series([100, 101, 102, 103], index=pd.to_datetime(
        ["2020-01-02", "2020-01-03", "2020-02-03", "2020-03-02"]))
    orders = backtest.dca_orders(series)
    assert len(orders) == 3
    assert [o.amount for o in orders] == pytest.approx([100 / 3] * 3)


def test_portfolio_accounting_and_max_drawdown():
    series = prices([100, 50, 100])
    path, metrics = backtest.portfolio_path(series, [backtest.Order(0, 50)])
    assert path.tolist() == pytest.approx([100, 75, 100])
    assert metrics["deployed"] == 50
    assert metrics["cash_remaining_pct"] == pytest.approx(50)
    assert metrics["max_drawdown_pct"] == pytest.approx(-25)
    assert metrics["average_entry_price"] == pytest.approx(100)


def test_portfolio_caps_orders_at_available_cash():
    _, metrics = backtest.portfolio_path(prices([10, 10]), [backtest.Order(0, 80), backtest.Order(1, 80)])
    assert metrics["deployed"] == 100
    assert metrics["cash_remaining_pct"] == pytest.approx(0)
    assert metrics["buys"] == 2


def test_funded_orders_drop_unfunded_later_signals():
    series = prices([10, 10, 10])
    orders = [backtest.Order(0, 50), backtest.Order(1, 50), backtest.Order(2, 50)]
    assert backtest.funded_orders(series, orders) == orders[:2]


def test_cash_rate_grows_idle_cash():
    _, metrics = backtest.portfolio_path(prices([100, 100]), [], cash_rate=.10)
    assert metrics["final_value"] > 100


def test_fast_terminal_accounting_matches_daily_accounting():
    series = prices([100, 90, 80, 95, 110])
    orders = [backtest.Order(1, 30), backtest.Order(3, 20)]
    _, metrics = backtest.portfolio_path(series, orders, cash_rate=.03, fee_bps=7)
    assert backtest.final_value_for_orders(series, orders, .03, 7) == pytest.approx(
        metrics["final_value"])


def test_episode_metric_counts_periods_not_days():
    actual = backtest.episode_metrics(prices([100, 95, 90, 99, 100, 95, 100]))
    assert actual["market_episodes"] == 2
    assert actual["average_episode_max_drawdown_pct"] == pytest.approx(-7.5)


def test_gpw_loader_uses_official_close_series(monkeypatch):
    import json

    payload = [{"data": [
        {"t": 1791151200, "c": 9564.75},
        {"t": 1791237600, "c": 9600.00},
    ]}]
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    captured = {}

    def fake_get(url, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return response

    monkeypatch.setattr(backtest.requests, "get", fake_get)
    result = backtest.load_gpw_wig20tr()
    request = json.loads(captured["params"]["req"])
    assert request[0]["isin"] == "PL9999999425"
    assert result.iloc[0] == pytest.approx(9564.75)
    assert result.index[0].date().isoformat() == "2026-10-05"


def test_evaluation_start_keeps_prior_high_for_signals_but_starts_fresh_cash():
    series = prices([100, 110, 99, 90, 80, 100])
    plans = backtest._strategy_orders(
        series.iloc[2:], (-10, -20), (), feature_prices=series, active_start=2)
    assert [(order.position, order.amount) for order in plans["current_ladder"]] == [
        (1, 50), (3, 50)]

