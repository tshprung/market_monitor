# Market Monitor

Tracks buy-tranche triggers for 6 index/ETF instruments and your
dividend-stock watchlist, and screens the dividend stocks against
fundamental filters. Sends one Telegram alert per run when there's
something to act on.

## The trigger engine (one engine, two modes)

`trigger_engine.py` has a single generic function that evaluates every
instrument the same way. Each instrument in `config.py` picks one of
two trigger *types* -- this is config data, not different code:

- **`drawdown_pct`** (default): reference price = the instrument's own
  rolling all-time high (within the fetched history window). Thresholds
  are % below that high, e.g. `[-8, -15, -25, -35]` -> 4 equal tranches.
  A new all-time high resets the cycle, so the same dip isn't bought twice.

- **`price_target`**: reference price = a fixed value you choose, e.g.
  BEZQ.TA at 428. It never moves upward even if the price rallies above
  it -- tranches accumulate downward from that fixed anchor. Thresholds
  are % further below the target (`0` = at/below the target itself).

Per-instrument overrides currently in `config.py`:
- **TA-35**: wider thresholds (`-15/-25/-35/-45` instead of the default
  `-8/-15/-25/-35`), because TA-35 rallied ~52% in 2025 and hit new highs
  into mid-2026 before June's correction -- the default -8% tranche would
  have fired almost immediately.
- **BEZQ.TA**: `price_target` anchored at 428 (your mid-2024 reference
  point) instead of a rolling high.

Everything else uses the default. Add or change overrides by editing
`config.py` -- no changes needed anywhere else.

Caveat: for `drawdown_pct`, "all-time high" is bounded by
`PRICE_HISTORY_PERIOD` (default 10y) -- free daily data doesn't reliably
go back further for all these markets. Good enough for a multi-year
cycle, not literally since-inception.

## Dividend fundamental screener

For each ticker in `DIVIDEND_INSTRUMENTS`:
- Yield >= 3%, payout ratio <= 70%, beta <= 1.0, Debt/EBITDA <= 4.0,
  positive free cash flow (`dividend_screener.py`)
- Piotroski F-Score >= 6/9, best-effort from yfinance's annual
  statements (`fundamentals.py`)

Every filter fails safe: missing data means that check does NOT pass.
**Price triggers are only evaluated for tickers currently passing every
fundamental filter** -- no point timing an entry into something that's
already failing on quality. If a stock later starts passing, its price
trigger picks up fresh from that point (no history is lost, it just
wasn't being tracked while it was failing).

## Setup

1. `pip install -r requirements.txt`
2. Push this repo to GitHub.
3. Add two repo secrets (Settings -> Secrets and variables -> Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. The workflow (`.github/workflows/monitor.yml`) runs weekdays at
   18:00 UTC, or trigger it manually from the Actions tab ("Run workflow").

## Known limitations (read before relying on this)

- This is a rules-based trigger, not a prediction. Thresholds are
  arbitrary and don't guarantee you buy at a real bottom.
- No index or dividend stock is crash-proof -- filters here select for
  lower historical volatility and financial quality, not immunity to loss.
- yfinance's `.info` and statement fields are best-effort and occasionally
  missing or delayed, especially for WIG20/TASE tickers -- check the
  Telegram "screening failed" / "data fetch failed" warnings if a name
  you expect never appears.
- Piotroski scores use partial data when some line items are missing, so
  they're a relative filter within your watchlist, not a precise external
  benchmark.
- `price_target` mode never resets, even if the price rallies far above
  the target -- if that's ever undesired for a ticker, say so and it can
  get a reset rule too (still via config, not special-cased code).
- Buy-vehicle tickers (`buy_ticker` in `config.py`) were confirmed
  available on XTB at time of writing; broker offerings change, so
  double check before placing an order.

Not financial advice.

## Backtest v2

Run `python backtest.py` to compare buy-and-hold, monthly DCA, the index
drawdown ladders configured above, a fixed -10/-20/-30% ladder, and an
expanding drawdown-percentile ladder. Example options:

```sh
python backtest.py --simulations 1000 --seed 42 --cash-rate 0.03 --fee-bps 5
python backtest.py --start 2000-01-01 --end 2025-01-01
python backtest.py --evaluation-start 2019-01-01
```

Percentile configurations available for comparison are 70/85/95, 75/90/95,
80/90/95, and 80/90/97. All four are included by default; `--percentiles 75 90 95`
runs only one configuration. These are fixed candidate
policies, not parameters selected for best historical performance. Each daily
severity rank compares today's drawdown only with drawdowns observed before
today; it requires 252 prior observations. The thresholds fire once per
high-watermark episode. The reference distribution uses daily drawdown
observations, so long episodes contribute more observations than short ones;
episode-level performance summaries separately count complete >=5% underwater
periods rather than individual days. The policy therefore makes decisions
walk-forward, without using future prices. The printed whole-history results are still
historical summaries, not proof that a configuration will work out of sample.
`--evaluation-start` adds a holdout-style run: it starts a fresh 100-unit
portfolio on that date while retaining earlier prices only for causal peak and
percentile references. No purchases before that date carry into the test.

Each instrument uses one series and one date range across strategies. Yahoo
Finance daily closes are used for S&P 500, Nasdaq 100, DAX, FTSE 100, and
TA-125, clipped to 1992-10-08 onward. WIG20TR comes from GPW Benchmark's public
daily chart data, available from 2012-12-03. The pooled portfolio uses the
shared overlap across instruments. Drawdown signals are observed at the close
and executed at the next available close. Scheduled DCA orders use
the first available close each calendar month; lump sum enters on the first
close. Initial capital is 100 index-currency units. Fees default to 0 bps and
idle cash earns 0% by default; both assumptions are explicit and configurable
with `--fee-bps` and `--cash-rate`. No currency conversion or slippage is
modeled. Annualized returns use elapsed calendar time. Maximum drawdown is
measured on daily portfolio value. Average entry price is cost-weighted for
shares bought. Cash remaining is terminal cash divided by starting capital.

The random-timing benchmark runs 1,000 seeded simulations per ladder. Each
simulation preserves that ladder's realized number and sizes of purchases but
assigns them to random distinct trading dates in the same period. This is a
conditional timing benchmark, not a test that the policy generalizes; the
reported upper-tail p-value is descriptive and does not establish significance.
Market drawdown episode counts and average episode troughs are printed so
consecutive days in one decline are not presented as independent episodes.

Series tested (Yahoo Finance `Close` where listed; no extra return adjustment):

| Report label | Yahoo ticker | Series caveat |
| --- | --- | --- |
| S&P 500 | `^GSPC` | Price index; excludes dividends. |
| Nasdaq 100 | `^NDX` | Price index; excludes dividends. |
| DAX | `^GDAXI` | DAX performance index; includes reinvested dividends by index design. |
| FTSE 100 | `^FTSE` | Price index; excludes dividends. |
| WIG20TR (for WIG20) | GPW Benchmark ISIN `PL9999999425` | Official GPW Benchmark close series; total-return index calculated since 2012-12-03. Backtest uses its levels for both drawdown features and portfolio returns. |
| TA-125 (configured as TA-35) | `^TA125.TA` | This is TA-125, not TA-35. TASE classifies TA-125 as gross total return; Yahoo's series was not reconciled against TASE's official history. Yahoo had no history for `^TA35.TA` in the check performed. |

The live config and Telegram labels are intentionally untouched. Backtest v2
reports the actual TA-125 series under its actual name and applies the wider
thresholds currently assigned to that config entry. Yahoo's WIG20 symbol still
has insufficient data, so WIG20TR from GPW Benchmark is used and labeled
explicitly. S&P 500, Nasdaq 100, and FTSE 100 are price series and omit
dividends; DAX is a performance index. Official TASE documentation classifies
TA-125 as gross total return, but Yahoo's series was not reconciled against its
official daily history, so comparisons that include TA-125 carry that caveat.
