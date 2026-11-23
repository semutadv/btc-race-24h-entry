"""BTC race bot: a dual-EMA trend follower for cbBTC (symbol CBBTC).

The idea in one paragraph
-------------------------
Bitcoin spends long stretches drifting one way and long stretches going
nowhere in particular. This bot only wants to own cbBTC while the drift is
up. It keeps two exponential moving averages of the one-minute closes -- a
fast one over roughly an hour (60 bars) and a slow one over roughly four
hours (240 bars). While the fast average sits above the slow one the market
is, by this simple yardstick, in an uptrend, so the bot puts 70% of its
cash to work. The moment the fast average slips back below the slow one it
sells the whole position and waits in cash until the fast average climbs
back above the slow one. The decision is purely a function of the current
state of the two averages -- there is no warm-up period and no waiting
for a crossover *event*: both averages are seeded at the first close and
update from bar zero, so if the state says "uptrend" on the very first
bar, the bot acts on it.

Why these choices
-----------------
* One position, all-or-nothing. With a single asset there is nothing to
  diversify into; the only real decision is "in or out", so the bot makes
  exactly that decision and nothing else.
* 70% sizing keeps a cash buffer. Fees, slippage and price impact are
  charged on every fill, and a full-cash buy would also leave nothing in
  reserve if a fill is partially rejected. Seventy percent is a deliberate
  compromise between exposure and friction.
* Wide slippage tolerance (100 bps). Orders fill at the *next* bar's open,
  so the price can move between decision and fill. A tight tolerance would
  see trend entries rejected on ordinary one-minute noise; 100 bps is wide
  enough to fill reliably while still capping a genuinely bad fill.
* Nothing fancy on purpose. No clock reads, no randomness, no network, no
  state beyond the two EMAs and whether we hold a position. The same bar
  stream always produces the same orders, which the replay requires.

Wire notes (from the vendored shim, vendor/makefun_bars.py)
------------------------------------------------------------
``state.cash`` is an int of raw USDC units (1e6 per dollar). A buy order
spends ``notional_quote_units``; a sell order names a raw ``qty`` taken
from ``state.positions["CBBTC"].qty``. Orders decided on one bar fill at
the next bar's open, so the bot never assumes a fill happened -- it reads
the account fresh from ``state`` on every batch. The bot updates its
averages on every batch, starting with the very first close, and orders
whenever the averages' state calls for it -- there is no warm-up gate.
"""

import os
import sys

# The grader runs this file with ``python3 -P -s``, which leaves the
# script's own directory off sys.path; put vendor/ on it explicitly.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"),
)

import makefun_bars  # noqa: E402  (vendored protocol shim)

SYMBOL = "CBBTC"

# Strategy parameters. The EMA spans are in one-minute bars: the fast
# average reacts within about an hour, the slow one anchors the day.
FAST_SPAN = 60
SLOW_SPAN = 240
# Fraction of current cash committed on an entry signal.
ENTRY_FRACTION = 0.70
# Slippage budget handed to the harness with every order, in bps.
MAX_SLIPPAGE_BPS = 100


class Ema:
    """One exponential moving average, seeded by its first sample.

    The smoothing factor is the textbook 2 / (span + 1). Seeding with the
    first observed close (rather than zero) keeps the average meaningful
    from the very first bar, at the cost of it being "younger" than its
    nominal span early on -- acceptable here because the bot acts on the
    averages' state from bar zero rather than sitting out a warm-up.
    """

    def __init__(self, span):
        self.alpha = 2.0 / (span + 1.0)
        self.value = None
        self.count = 0

    def update(self, sample):
        """Fold one new close into the average and return the average."""
        if self.value is None:
            self.value = float(sample)
        else:
            self.value += self.alpha * (sample - self.value)
        self.count += 1
        return self.value


class TrendBot:
    """The strategy itself, deliberately decoupled from the wire.

    Feed it closes one bar at a time through :meth:`on_close`, telling it
    whether a position is currently held, and it answers with an intent:
    ``"buy"``, ``"sell"`` or ``None``. It owns no account state of its
    own, which is what lets a local simulator drive the exact same code
    the live bot runs.
    """

    def __init__(self, fast_span=FAST_SPAN, slow_span=SLOW_SPAN):
        self.fast = Ema(fast_span)
        self.slow = Ema(slow_span)
        self.slow_span = slow_span

    def on_close(self, close, holding):
        """Advance both averages with ``close`` and decide the intent.

        ``holding`` is True when a CBBTC position is open. Both averages
        are seeded at the first close and update from bar zero, and the
        intent is state-based rather than crossover-based: flat with the
        fast average above the slow one buys, holding with the fast
        average below the slow one sells, anything else does nothing.
        """
        fast = self.fast.update(close)
        slow = self.slow.update(close)
        if not holding and fast > slow:
            return "buy"
        if holding and fast < slow:
            return "sell"
        return None


# One bot instance for the whole run; the shim calls on_batch once per bar.
_BOT = TrendBot()


def on_batch(state, batch):
    """Shim callback: translate the bot's intent into at most one order.

    The position check reads ``state.positions`` as the harness reports
    it, so a rejected or still-pending order can never trick the bot into
    double-buying or selling something it does not hold.
    """
    close = state.close(SYMBOL)
    if close is None:
        # No bar for CBBTC in this batch: nothing to learn, nothing to do.
        return []
    holding = SYMBOL in state.positions and state.positions[SYMBOL].qty > 0
    intent = _BOT.on_close(close, holding)
    if intent is None:
        return []
    if intent == "buy":
        notional = int(state.cash * ENTRY_FRACTION)
        if notional <= 0:
            return []
        return [
            {
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": notional,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]
    # intent == "sell": exit the entire position, whatever it now is.
    qty = state.positions[SYMBOL].qty
    return [
        {
            "side": "sell",
            "symbol": SYMBOL,
            "qty": qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }
    ]


if __name__ == "__main__":
    makefun_bars.run(on_batch)
