# Market Monitor

Tracks drawdown-based buy tranches for 6 index/ETF instruments, and
screens a dividend-stock watchlist against fundamental filters. Sends
one Telegram alert per run when there's something to act on.

## How it decides when to buy an index

- Tracks the highest close price seen (within the fetched history window).
- When price drops below that high by a threshold, it fires a signal to
  buy a tranche of your planned allocation:

  | Drawdown from high | Tranche |
  |---|---|
  | -8% | 25% |
  | -15% | 25% |
  | -25% | 25% |
  | -35% | remaining 25% |

- A new all-time high resets the cycle (so the same dip isn't bought twice).
- Edit thresholds/tranche sizes in `config.py`.

Caveat: "all-time high" is bounded by the fetched history window
(`PRICE_HISTORY_PERIOD`, default 10y) -- free daily data doesn't reliably
go back further for all 6 markets. Good enough for a multi-year cycle,
not literally since-inception.

## How the dividend screener works

For each ticker in `DIVIDEND_WATCHLIST` (`config.py`):
- Yield >= 3%, payout ratio <= 70%, beta <= 1.0, Debt/EBITDA <= 4.0,
  positive free cash flow (via `dividend_screener.py`)
- Piotroski F-Score >= 6/9, best-effort from yfinance's annual statements
  (via `fundamentals.py`)

Every filter fails safe: if a data field is missing, that check does NOT
pass. A ticker only surfaces in an alert if every filter has enough data
and clears its bar.

## Setup

1. `pip install -r requirements.txt`
2. Push this repo to GitHub.
3. Add two repo secrets (Settings -> Secrets and variables -> Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. The workflow runs weekdays at 18:00 UTC, or trigger it manually from
   the Actions tab ("Run workflow").

## Known limitations (read before relying on this)

- This is a rules-based trigger, not a prediction. Drawdown thresholds
  are arbitrary and don't guarantee you buy at a real bottom.
- No index or dividend stock is crash-proof -- this filters for lower
  historical volatility and financial quality, not immunity to loss.
- yfinance's `.info` and statement fields are best-effort and occasionally
  missing or delayed, especially for WIG20/TASE tickers -- check the
  Telegram "screening failed" warnings if a name you expect never appears.
- Piotroski scores use partial data when some line items are missing, so
  they're a relative filter within your watchlist, not a precise external
  benchmark.
- Buy vehicle tickers (`buy_ticker` in `config.py`) were confirmed
  available on XTB at time of writing; broker offerings change, so
  double check before placing an order.

Not financial advice.
# market_monitor
