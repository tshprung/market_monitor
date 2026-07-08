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
