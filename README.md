# Race a BTC trading bot live for 24 hours

[![Competition](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511)
[![Rank](https://make.fun/badge/btc-race-24h-20261123-0511/semutadv/btc-race-24h-entry/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard)
[![Reward](https://make.fun/badge/btc-race-24h-20261123-0511/semutadv/btc-race-24h-entry/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511)

My entry for the make.fun BTC race: a small Python bot that trades
Coinbase Wrapped BTC (cbBTC, symbol `CBBTC`) minute by minute on $1,000 of
paper money. Nothing real is traded — the bot reads one-minute bars of the
cbBTC/USDC pool and answers each bar with at most one order. Orders are
decided on one bar and fill at the next bar's open, paying a 4 bps fee,
2 bps of slippage and the order's own price impact on the pool.

## Strategy: ride the trend, sit out the rest

The bot keeps two exponential moving averages of the one-minute closes:

- a **fast EMA over 60 bars** (about an hour), and
- a **slow EMA over 240 bars** (about four hours).

The rules are deliberately minimal:

1. **Flat and fast above slow → buy** with 70% of the current cash.
2. **Holding and fast below slow → sell** the entire position.
3. Otherwise, do nothing.

That is the whole strategy. cbBTC drifts in persistent intraday trends,
and a dual-EMA crossover is the simplest robust way to be long for those
drifts and in cash for the rest, without predicting anything. The 70%
sizing leaves a buffer against fill friction and partial rejections, and
the all-or-nothing exit avoids a ladder of small sells each paying the
fixed per-fill costs again. Every order carries a 100 bps slippage budget
so an entry decided on one bar is not rejected by ordinary noise at the
next bar's open.

The strategy is implemented as a standalone `TrendBot` class in
`main.py`: it consumes closes and reports an intent (`buy` / `sell` /
none), with no knowledge of the wire protocol. The thin `on_batch`
wrapper around it reads the account from the protocol state on every
batch, so the bot can never act on a stale idea of what it holds.

## How it runs

```
python3 main.py
```

The bot speaks the `agent-fun/bars-replay/v1` protocol over stdin/stdout
through the vendored shim in `vendor/makefun_bars.py` (copied unchanged
from the competition kit's SDK). It uses only the Python 3.13 standard
library, reads no clock, no environment and no network, and uses no
randomness — the same bar stream always yields the same orders.

## Local check

`sim.py` is a development tool (not part of the entry). It replays the
frozen dev window from the kit through the same `TrendBot`, filling at
next-bar opens with the 6 bps per-side cost plus price impact, and prints
the net PnL, the number of fills and the maximum drawdown:

```
python3 sim.py
```

## License

MIT — see `LICENSE`.
