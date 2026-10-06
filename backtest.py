"""Causal, apples-to-apples backtests for the index drawdown policies.

Signals are calculated from closes known at the time. Drawdown-policy orders
execute at the *next* available close; buy-and-hold and scheduled DCA use their
known-in-advance dates. Yahoo Finance close series are the common data source.
See README.md for the tested series, limitations, and accounting assumptions.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from config import INDEX_INSTRUMENTS

# The desktop sandbox may not expose Yahoo's default per-user SQLite cache.
_yf_cache = os.path.join(tempfile.gettempdir(), "market_monitor_yfinance")
os.makedirs(_yf_cache, exist_ok=True)
yf.set_tz_cache_location(_yf_cache)

INITIAL_CAPITAL = 100.0
PERCENTILE_CONFIGS = ((70, 85, 95), (75, 90, 95), (80, 90, 95), (80, 90, 97))
MIN_PERCENTILE_HISTORY = 252
DEFAULT_SIMULATIONS = 1000
GPW_WIG20TR_ISIN = "PL9999999425"
GPW_CHART_URL = "https://gpwbenchmark.pl/chart-json.php"


@dataclass(frozen=True)
class Order:
    position: int
    amount: float


def load_prices(ticker: str, start: str | None = None, end: str | None = None) -> pd.Series:
    """Fetch one unadjusted daily Close series; no cross-source splicing."""
    data = yf.Ticker(ticker).history(
        period="max" if start is None and end is None else None,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        actions=False,
    )
    if data.empty or "Close" not in data:
        raise ValueError(f"No daily Close history returned for {ticker}")
    prices = data["Close"].dropna().astype(float)
    prices.index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
    prices = prices[~prices.index.duplicated(keep="last")].sort_index()
    if len(prices) < 2 or (prices <= 0).any():
        raise ValueError(f"Insufficient or invalid daily Close history for {ticker}")
    return prices


def load_gpw_wig20tr(start: str = "2012-12-03", end: str | None = None) -> pd.Series:
    """Fetch official GPW Benchmark WIG20TR closes from its public chart API."""
    end_date = (pd.Timestamp(end).date() - pd.Timedelta(days=1)).isoformat() if end else (
        pd.Timestamp.now().date() + pd.Timedelta(days=1)).isoformat()
    req = [{"isin": GPW_WIG20TR_ISIN, "mode": "RANGE", "from": start, "to": end_date}]
    response = requests.get(
        GPW_CHART_URL,
        params={"req": json.dumps(req, separators=(",", ":")),
                "t": int(time.time() * 1000)},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    records = payload[0].get("data", []) if payload else []
    if not records:
        raise ValueError("GPW Benchmark returned no WIG20TR history")
    dates = pd.to_datetime([item["t"] for item in records], unit="s", utc=True)
    dates = dates.tz_convert("Europe/Warsaw").tz_localize(None).normalize()
    prices = pd.Series([float(item["c"]) for item in records], index=dates,
                       name="WIG20TR").dropna().sort_index()
    if len(prices) < 2 or (prices <= 0).any():
        raise ValueError("GPW Benchmark returned insufficient or invalid WIG20TR history")
    return prices


def drawdowns(prices: pd.Series) -> pd.Series:
    """Causal close-to-running-high drawdowns, as decimals (e.g. -0.2)."""
    if (prices <= 0).any():
        raise ValueError("prices must be positive")
    return prices / prices.cummax() - 1.0


def expanding_severity_percentile(values: pd.Series, min_periods: int = 1) -> pd.Series:
    """Percentile severity of each observation vs *prior* values only.

    A result of 90 means that 90% of previously observed drawdowns were less
    severe (greater or equal numerically) than today's. Today's value is never
    included in its own reference distribution.
    """
    a = values.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    history: list[float] = []
    sorted_history: list[float] = []
    import bisect

    for i, value in enumerate(a):
        if len(history) >= min_periods:
            # Number of historical values >= today's observation.
            first_ge = bisect.bisect_left(sorted_history, value)
            out[i] = (len(sorted_history) - first_ge) / len(sorted_history) * 100.0
        bisect.insort(sorted_history, value)
        history.append(value)
    return pd.Series(out, index=values.index, name="severity_percentile")


def drawdown_orders(prices: pd.Series, thresholds: tuple[float, ...],
                    amounts: tuple[float, ...]) -> list[Order]:
    """Current/fixed ladders; one firing per threshold per high-water cycle."""
    return _ladder_orders(prices, thresholds, amounts)


def _ladder_orders(prices: pd.Series, thresholds: tuple[float, ...],
                   amounts: tuple[float, ...], active_start: int = 0) -> list[Order]:
    if len(thresholds) != len(amounts):
        raise ValueError("thresholds and amounts must have the same length")
    dd = drawdowns(prices).to_numpy()
    high = np.maximum.accumulate(prices.to_numpy())
    triggered: set[int] = set()
    orders: list[Order] = []
    for i in range(max(1, active_start), len(prices) - 1):  # next-close fill
        if prices.iloc[i] > high[i - 1]:
            triggered.clear()
            continue
        for rung, (threshold, amount) in enumerate(zip(thresholds, amounts)):
            if rung not in triggered and dd[i] <= threshold + 1e-12:
                orders.append(Order(i + 1, amount))
                triggered.add(rung)
    return orders


def percentile_orders(prices: pd.Series, levels: tuple[int, ...],
                      active_start: int = 0) -> list[Order]:
    if tuple(sorted(levels)) != levels or len(set(levels)) != len(levels):
        raise ValueError("percentile levels must be unique and increasingly extreme")
    dd = drawdowns(prices)
    severity = expanding_severity_percentile(dd, MIN_PERCENTILE_HISTORY)
    triggered: set[int] = set()
    high = np.maximum.accumulate(prices.to_numpy())
    orders: list[Order] = []
    amount = INITIAL_CAPITAL / len(levels)
    for i in range(max(1, active_start), len(prices) - 1):
        if prices.iloc[i] > high[i - 1]:
            triggered.clear()
            continue
        if pd.isna(severity.iloc[i]):
            continue
        for rung, level in enumerate(levels):
            if rung not in triggered and severity.iloc[i] >= level:
                orders.append(Order(i + 1, amount))
                triggered.add(rung)
    return orders


def dca_orders(prices: pd.Series) -> list[Order]:
    """One equal contribution per calendar month, at first available close."""
    groups = pd.Series(np.arange(len(prices)), index=prices.index).groupby(
        [prices.index.year, prices.index.month], sort=True
    )
    positions = [int(group.iloc[0]) for _, group in groups]
    amount = INITIAL_CAPITAL / len(positions)
    return [Order(pos, amount) for pos in positions]


def portfolio_path(prices: pd.Series, orders: list[Order], cash_rate: float = 0.0,
                   fee_bps: float = 0.0) -> tuple[pd.Series, dict[str, float]]:
    """Account for shares, cash yield and fees; orders spend no more than cash."""
    if cash_rate <= -1 or fee_bps < 0 or fee_bps >= 10000:
        raise ValueError("cash rate must exceed -100%; fee bps must be in [0, 10000)")
    by_position: dict[int, list[float]] = {}
    for order in orders:
        by_position.setdefault(order.position, []).append(order.amount)
    cash, shares, deployed, buys = INITIAL_CAPITAL, 0.0, 0.0, 0
    values = []
    entry_prices: list[float] = []
    cash_daily = (1.0 + cash_rate) ** (1.0 / 252.0)
    fee_rate = fee_bps / 10000.0
    prices_array = prices.to_numpy(dtype=float)
    for i, price in enumerate(prices_array):
        if i:
            cash *= cash_daily
        for amount in by_position.get(i, []):
            spend = min(float(amount), cash)
            net = spend / (1.0 + fee_rate)
            shares += net / price
            cash -= spend
            deployed += spend
            if spend > 0:
                buys += 1
                entry_prices.append(float(price))
        values.append(cash + shares * price)
    path = pd.Series(values, index=prices.index, name="portfolio_value")
    average_entry = deployed / shares if shares else math.nan
    metrics = {
        "final_value": float(path.iloc[-1]),
        "total_return_pct": (float(path.iloc[-1]) / INITIAL_CAPITAL - 1) * 100,
        "annualized_return_pct": ((float(path.iloc[-1]) / INITIAL_CAPITAL) **
                                  (365.25 / (prices.index[-1] - prices.index[0]).days) - 1) * 100,
        "max_drawdown_pct": float((path / path.cummax() - 1).min() * 100),
        "average_entry_price": float(average_entry),
        "deployed": float(deployed),
        "cash_remaining_pct": float(cash / INITIAL_CAPITAL * 100),
        "buys": int(buys),
        "worst_entry": float(max(entry_prices, default=math.nan)),
        "best_entry": float(min(entry_prices, default=math.nan)),
    }
    return path, metrics


def funded_orders(prices: pd.Series, orders: list[Order], cash_rate: float = 0.0,
                  fee_bps: float = 0.0) -> list[Order]:
    """Keep only actual fills, preserving a partial final tranche if needed."""
    cash = INITIAL_CAPITAL
    daily_growth = (1.0 + cash_rate) ** (1.0 / 252.0)
    last_position = 0
    funded: list[Order] = []
    for order in sorted(orders, key=lambda item: item.position):
        cash *= daily_growth ** (order.position - last_position)
        spend = min(float(order.amount), cash)
        if spend > 1e-12:
            funded.append(Order(order.position, spend))
            cash -= spend
        last_position = order.position
    return funded


def final_value_for_orders(prices: pd.Series, orders: list[Order], cash_rate: float = 0.0,
                          fee_bps: float = 0.0) -> float:
    """Fast terminal value calculation for Monte Carlo paths (no daily series)."""
    if cash_rate <= -1 or fee_bps < 0 or fee_bps >= 10000:
        raise ValueError("cash rate must exceed -100%; fee bps must be in [0, 10000)")
    daily_growth = (1.0 + cash_rate) ** (1.0 / 252.0)
    fee_rate = fee_bps / 10000.0
    cash, shares, last_day = INITIAL_CAPITAL, 0.0, 0
    for order in sorted(orders, key=lambda o: o.position):
        cash *= daily_growth ** (order.position - last_day)
        spend = min(order.amount, cash)
        shares += (spend / (1.0 + fee_rate)) / float(prices.iloc[order.position])
        cash -= spend
        last_day = order.position
    cash *= daily_growth ** (len(prices) - 1 - last_day)
    return float(cash + shares * float(prices.iloc[-1]))


def episode_metrics(prices: pd.Series) -> dict[str, float]:
    """Count >=5% below-high episodes, not individual underwater days."""
    dd = drawdowns(prices)
    troughs: list[float] = []
    in_episode = False
    trough = 0.0
    for value in dd.to_numpy():
        if value < 0 and not in_episode:
            in_episode, trough = True, float(value)
        elif in_episode and value < 0:
            trough = min(trough, float(value))
        elif in_episode:
            if trough <= -.05:
                troughs.append(trough * 100)
            in_episode = False
    if in_episode and trough <= -.05:  # include a right-censored final episode
        troughs.append(trough * 100)
    return {"market_episodes": len(troughs),
            "average_episode_max_drawdown_pct": float(np.mean(troughs)) if troughs else 0.0}


def _random_orders(base_orders: list[Order], n_dates: int, rng: np.random.Generator) -> list[Order]:
    if not base_orders:
        return []
    positions = np.sort(rng.choice(np.arange(n_dates), size=min(len(base_orders), n_dates), replace=False))
    return [Order(int(pos), order.amount) for pos, order in zip(positions, base_orders)]


def _strategy_orders(prices: pd.Series, current_thresholds: tuple[float, ...],
                     percentile_configs: tuple[tuple[int, ...], ...],
                     feature_prices: pd.Series | None = None,
                     active_start: int = 0) -> dict[str, list[Order]]:
    feature_prices = feature_prices if feature_prices is not None else prices
    current_amount = INITIAL_CAPITAL / len(current_thresholds)
    plans = {
        "buy_hold": [Order(0, INITIAL_CAPITAL)],
        "monthly_dca": dca_orders(prices),
        "current_ladder": _ladder_orders(
            feature_prices, tuple(t / 100 for t in current_thresholds),
            tuple(current_amount for _ in current_thresholds), active_start),
        "fixed_10_20_30": _ladder_orders(
            feature_prices, (-.10, -.20, -.30), (INITIAL_CAPITAL / 3,) * 3,
            active_start),
    }
    for config in percentile_configs:
        plans["percentile_" + "_".join(map(str, config))] = percentile_orders(
            feature_prices, config, active_start)
    if active_start:
        for strategy in ("current_ladder", "fixed_10_20_30", *[
                "percentile_" + "_".join(map(str, config)) for config in percentile_configs]):
            plans[strategy] = [Order(order.position - active_start, order.amount)
                               for order in plans[strategy] if order.position > active_start]
    return plans


def run_instrument(name: str, ticker: str, thresholds: tuple[float, ...],
                   prices: pd.Series, simulations: int, seed: int,
                   cash_rate: float, fee_bps: float,
                   percentile_configs: tuple[tuple[int, ...], ...],
                   evaluation_start: str | None = None) -> tuple[list[dict], dict, dict[str, pd.Series]]:
    if len(prices) < MIN_PERCENTILE_HISTORY + 2:
        raise ValueError(f"only {len(prices)} daily observations; need at least "
                         f"{MIN_PERCENTILE_HISTORY + 2} for percentile policy")
    active_start = (int(prices.index.searchsorted(pd.Timestamp(evaluation_start)))
                    if evaluation_start else 0)
    if active_start >= len(prices) - 1:
        raise ValueError(f"no test data after evaluation start {evaluation_start}")
    test_prices = prices.iloc[active_start:]
    plans = _strategy_orders(test_prices, thresholds, percentile_configs,
                             feature_prices=prices, active_start=active_start)
    rows: list[dict] = []
    paths: dict[str, pd.Series] = {}
    random_stats: dict[str, dict] = {}
    rng = np.random.default_rng(seed)
    for strategy, orders in plans.items():
        actual_orders = funded_orders(test_prices, orders, cash_rate, fee_bps)
        path, metrics = portfolio_path(test_prices, actual_orders, cash_rate, fee_bps)
        paths[strategy] = path
        rows.append({"instrument": name, "ticker": ticker, "strategy": strategy,
                     **metrics, **episode_metrics(test_prices)})
        if strategy not in ("buy_hold", "monthly_dca") and simulations > 0:
            random_values = []
            for _ in range(simulations):
                random_orders = _random_orders(actual_orders, len(test_prices), rng)
                random_values.append(final_value_for_orders(test_prices, random_orders,
                                                            cash_rate, fee_bps))
            values = np.asarray(random_values)
            random_stats[strategy] = {
                "random_median": float(np.median(values)),
                "random_p05": float(np.quantile(values, .05)),
                "random_p95": float(np.quantile(values, .95)),
                "random_percentile": float((values < metrics["final_value"]).mean() * 100),
                "random_upper_tail_p": float((1 + (values >= metrics["final_value"]).sum()) /
                                              (len(values) + 1)),
            }
    for row in rows:
        row.update(random_stats.get(row["strategy"], {}))
    return rows, {"start": test_prices.index[0].date().isoformat(),
                  "end": test_prices.index[-1].date().isoformat(),
                  "observations": len(test_prices), **episode_metrics(test_prices)}, paths


def _print_report(rows: list[dict], coverage: dict[str, dict],
                  portfolio_paths: dict[str, dict[str, pd.Series]], cash_rate: float,
                  fee_bps: float, simulations: int,
                  pooled_start: str) -> None:
    df = pd.DataFrame(rows)
    cols = ["instrument", "strategy", "final_value", "total_return_pct",
            "annualized_return_pct", "max_drawdown_pct", "average_entry_price",
            "deployed", "cash_remaining_pct", "buys", "random_percentile"]
    fmt = {k: (lambda x: "—" if pd.isna(x) else f"{x:.2f}") for k in cols
           if k not in ("instrument", "strategy", "buys")}
    print("\n=== Backtest v2 (initial capital = 100 index-currency units) ===")
    print(f"cash annual rate={cash_rate:.2%}; transaction fee={fee_bps:.1f} bps; "
          f"random simulations={simulations}; random seed=42")
    print(df[cols].to_string(index=False, formatters=fmt))
    print("\nRandom timing distribution by strategy (p05 / median / p95 and strategy percentile):")
    for row in rows:
        if "random_median" in row:
            print(f"{row['instrument']} {row['strategy']}: "
                  f"{row['random_p05']:.2f} / {row['random_median']:.2f} / "
                  f"{row['random_p95']:.2f}; percentile="
                  f"{row['random_percentile']:.1f}%, one-sided upper-tail p="
                  f"{row['random_upper_tail_p']:.3f}")
    print(f"\nPooled equal-weight portfolio (fresh 100-unit allocation per index from "
          f"{pooled_start}; common history only):")
    pooled_rows = []
    for strategy, per_instrument in portfolio_paths.items():
        calendar = per_instrument[next(iter(per_instrument))].index
        for path in per_instrument.values():
            calendar = calendar.union(path.index)
        wealth = pd.concat([p.div(INITIAL_CAPITAL).reindex(calendar).ffill()
                            for p in per_instrument.values()], axis=1).dropna()
        pooled_path = wealth.mean(axis=1) * INITIAL_CAPITAL
        years = (pooled_path.index[-1] - pooled_path.index[0]).days / 365.25
        pooled_rows.append({
            "strategy": strategy,
            "final_value_per_100_per_index": float(pooled_path.iloc[-1]),
            "total_return_pct": (float(pooled_path.iloc[-1]) / INITIAL_CAPITAL - 1) * 100,
            "annualized_return_pct": ((float(pooled_path.iloc[-1]) / INITIAL_CAPITAL) **
                                      (1 / years) - 1) * 100,
            "max_drawdown_pct": float((pooled_path / pooled_path.cummax() - 1).min() * 100),
        })
    pooled = pd.DataFrame(pooled_rows)
    print(pooled.to_string(index=False, formatters={c: (lambda x: f"{x:.2f}")
          for c in pooled.columns if c != "strategy"}))
    print("\nCoverage:")
    for name, info in coverage.items():
        print(f"{name}: {info['start']} to {info['end']} ({info['observations']} closes), "
              f"{info['market_episodes']} drawdown episodes, mean episode trough "
              f"{info['average_episode_max_drawdown_pct']:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="optional common start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="optional exclusive end date (YYYY-MM-DD)")
    parser.add_argument("--evaluation-start", help=(
        "start a fresh test portfolio on this date while using earlier closes "
        "only to form causal drawdown features (YYYY-MM-DD)"))
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cash-rate", type=float, default=0.0,
                        help="annual effective cash return (default: 0; e.g. 0.03 for 3%%)")
    parser.add_argument("--fee-bps", type=float, default=0.0,
                        help="transaction fee per purchase in basis points (default: 0)")
    parser.add_argument("--percentiles", type=int, nargs=3,
                        metavar=("FIRST", "SECOND", "THIRD"),
                        help="optionally run only one config; default runs all four documented configs")
    args = parser.parse_args()
    pcs = (tuple(args.percentiles),) if args.percentiles else PERCENTILE_CONFIGS
    if any(pc not in PERCENTILE_CONFIGS for pc in pcs):
        parser.error(f"--percentiles must be one of {PERCENTILE_CONFIGS}")
    rows, coverage, portfolio_paths, prices_by_instrument = [], {}, {}, {}
    metadata_by_instrument = {}
    for name, meta in INDEX_INSTRUMENTS.items():
        ticker = meta["signal_ticker"]
        # The live config currently labels ^TA125.TA as TA-35. Preserve the
        # live alert config while reporting the instrument actually fetched.
        report_name = "TA-125 (configured as TA-35)" if ticker == "^TA125.TA" else name
        try:
            if name == "WIG20":
                report_name = "WIG20TR"
                ticker = f"GPW Benchmark WIG20TR ({GPW_WIG20TR_ISIN})"
                prices = load_gpw_wig20tr(args.start or "2012-12-03", args.end)
            else:
                prices = load_prices(ticker, args.start, args.end)
                if args.start is None and args.end is None:
                    prices = prices.loc["1992-10-08":]
            trigger = meta["trigger"]
            instrument_rows, info, paths = run_instrument(
                report_name, ticker, tuple(trigger["thresholds"]), prices,
                args.simulations, args.seed, args.cash_rate, args.fee_bps, pcs,
                args.evaluation_start,
            )
            rows.extend(instrument_rows)
            coverage[report_name] = info
            prices_by_instrument[report_name] = prices
            metadata_by_instrument[report_name] = (ticker, tuple(trigger["thresholds"]))
        except Exception as exc:
            print(f"\n{name} ({ticker}): EXCLUDED — {exc}")
    if not rows:
        raise SystemExit("No instruments had sufficient reliable history")
    common_start = max(series.index[0] for series in prices_by_instrument.values())
    pooled_start_ts = max(pd.Timestamp(args.evaluation_start), common_start) \
        if args.evaluation_start else common_start
    pooled_start = pooled_start_ts.date().isoformat()
    for instrument, prices in prices_by_instrument.items():
        ticker, thresholds = metadata_by_instrument[instrument]
        _, _, common_paths = run_instrument(
            instrument, ticker, thresholds, prices, 0, args.seed, args.cash_rate,
            args.fee_bps, pcs, evaluation_start=pooled_start,
        )
        for strategy, path in common_paths.items():
            portfolio_paths.setdefault(strategy, {})[instrument] = path
    _print_report(rows, coverage, portfolio_paths, args.cash_rate, args.fee_bps,
                  args.simulations, pooled_start)


if __name__ == "__main__":
    main()
