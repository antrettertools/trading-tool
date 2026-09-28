"""Paper-trading engine: order matching, position tracking, P&L, persistence.

Net-position model (one position per ticker). Filling an order that reduces or
flips the position realizes P&L on the closed quantity and records a closed
trade. Equity = starting_balance + realized_pnl + unrealized_pnl.

Runs entirely off the live price feed; emits Qt signals so the UI refreshes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from trading.orders import Order, BUY, SELL, OPEN, FILLED, CANCELLED


@dataclass
class Position:
    ticker: str
    qty: float = 0.0          # signed: + long, - short
    avg_price: float = 0.0

    @property
    def is_flat(self) -> bool:
        return abs(self.qty) < 1e-9


class PaperEngine(QObject):
    orders_changed = Signal()
    position_changed = Signal()
    account_changed = Signal()
    fill_event = Signal(object)        # Order
    trade_closed = Signal(object)      # trade dict

    def __init__(self, db, starting_balance: float):
        super().__init__()
        self.db = db
        self.starting_balance = starting_balance
        acct = db.get_account(starting_balance)
        self.starting_balance = acct["starting_balance"]
        self.realized_pnl = acct["realized_pnl"]
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.last_price: dict[str, float] = {}

    def load_ticker(self, ticker: str):
        """Load open orders + reconstruct net position from trades for a ticker."""
        self.orders = [o for o in self.orders if o.ticker != ticker]
        for row in self.db.get_orders(ticker, status=OPEN):
            self.orders.append(Order.from_db(row))
        self._reconstruct_position(ticker)
        self.orders_changed.emit()
        self.position_changed.emit()

    # ------------------------------------------------------------------ orders
    def submit(self, order: Order) -> Order:
        order.id = self.db.insert_order(order.to_db())
        self.orders.append(order)
        # market or immediately-marketable orders fill on next/current price
        price = self.last_price.get(order.ticker)
        if price is not None:
            self._try_fill(order, price)
        self.orders_changed.emit()
        return order

    def cancel(self, order: Order):
        if order.status == OPEN:
            order.status = CANCELLED
            self.db.update_order(order.id, status=CANCELLED)
            self.orders_changed.emit()

    def cancel_all(self, ticker: str | None = None):
        for o in self.orders:
            if o.status == OPEN and (ticker is None or o.ticker == ticker):
                o.status = CANCELLED
                self.db.update_order(o.id, status=CANCELLED)
        self.orders_changed.emit()

    def open_orders(self, ticker: str | None = None) -> list[Order]:
        return [o for o in self.orders if o.status == OPEN
                and (ticker is None or o.ticker == ticker)]

    # ------------------------------------------------------------------ pricing
    def on_price(self, ticker: str, price: float):
        self.last_price[ticker] = price
        filled_any = False
        for o in list(self.orders):
            if o.status == OPEN and o.ticker == ticker:
                if self._try_fill(o, price):
                    filled_any = True
        # unrealized P&L moves with price
        if ticker in self.positions and not self.positions[ticker].is_flat:
            self.position_changed.emit()
            self.account_changed.emit()
        if filled_any:
            self.orders_changed.emit()

    def _try_fill(self, order: Order, price: float) -> bool:
        fp = order.check_fill(price)
        if fp is None:
            return False
        order.status = FILLED
        order.fill_price = fp
        order.filled_at = time.time()
        self.db.update_order(order.id, status=FILLED, fill_price=fp,
                             filled_at=order.filled_at)
        self._apply_fill(order, fp)
        self.fill_event.emit(order)
        self.position_changed.emit()
        self.account_changed.emit()
        return True

    # ------------------------------------------------------------------ positions
    @staticmethod
    def _update_position(pos: Position, signed: float, price: float):
        """Apply a signed fill to a position. Returns close-info dict if the
        fill closed/reduced/flipped the position (for realizing P&L), else None.
        Pure: mutates only ``pos`` so it can be reused for reconstruction."""
        old_qty = pos.qty
        if old_qty == 0 or (old_qty > 0) == (signed > 0):
            # opening or increasing in same direction -> blend avg price
            new_qty = old_qty + signed
            pos.avg_price = (pos.avg_price * abs(old_qty) + price * abs(signed)) \
                / abs(new_qty) if new_qty != 0 else 0.0
            pos.qty = new_qty
            return None
        # reducing / closing / flipping
        closing = min(abs(signed), abs(old_qty))
        direction = 1 if old_qty > 0 else -1
        entry = pos.avg_price
        realized = (price - entry) * closing * direction
        remaining = abs(signed) - closing
        new_qty = old_qty + signed
        pos.qty = new_qty
        if remaining > 1e-9:            # flipped to the other side
            pos.avg_price = price
        elif abs(new_qty) < 1e-9:
            pos.avg_price = 0.0
        return {"closing": closing, "direction": direction,
                "entry": entry, "realized": realized}

    def _apply_fill(self, order: Order, price: float):
        pos = self.positions.setdefault(order.ticker, Position(order.ticker))
        signed = order.qty if order.side == BUY else -order.qty
        close = self._update_position(pos, signed, price)
        if close:
            self.realized_pnl += close["realized"]
            self.db.update_account(realized_pnl=self.realized_pnl,
                                   cash=self.starting_balance + self.realized_pnl)
            trade = {
                "ticker": order.ticker,
                "side": "long" if close["direction"] > 0 else "short",
                "qty": close["closing"], "entry_price": close["entry"],
                "exit_price": price, "pnl": close["realized"],
                "entry_ts": order.created_at, "exit_ts": time.time(),
            }
            self.db.insert_trade(trade)
            self.trade_closed.emit(trade)

    def _reconstruct_position(self, ticker: str):
        """Rebuild the open net position by replaying filled orders. Realized
        P&L is NOT re-applied (it's already persisted on the account)."""
        filled = self.db.get_orders(ticker, status=FILLED)
        filled.sort(key=lambda r: (r.get("filled_at") or r["created_at"]))
        pos = Position(ticker)
        for row in filled:
            if row.get("fill_price") is None:
                continue
            signed = row["qty"] if row["side"] == BUY else -row["qty"]
            self._update_position(pos, signed, row["fill_price"])
        if not pos.is_flat:
            self.positions[ticker] = pos
        elif ticker in self.positions:
            del self.positions[ticker]

    # ------------------------------------------------------------------ account
    def unrealized_pnl(self) -> float:
        total = 0.0
        for t, pos in self.positions.items():
            if pos.is_flat:
                continue
            price = self.last_price.get(t, pos.avg_price)
            total += (price - pos.avg_price) * pos.qty
        return total

    def equity(self) -> float:
        return self.starting_balance + self.realized_pnl + self.unrealized_pnl()

    def position_pnl(self, ticker: str):
        pos = self.positions.get(ticker)
        if not pos or pos.is_flat:
            return 0.0, 0.0
        price = self.last_price.get(ticker, pos.avg_price)
        pnl = (price - pos.avg_price) * pos.qty
        pct = (price / pos.avg_price - 1) * 100 * (1 if pos.qty > 0 else -1) \
            if pos.avg_price else 0.0
        return pnl, pct

    def stats(self) -> dict:
        trades = self.db.get_trades()
        wins = [t for t in trades if t["pnl"] > 0]
        return {
            "starting_balance": self.starting_balance,
            "equity": self.equity(),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl(),
            "total_trades": len(trades),
            "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        }

    def reset(self):
        self.db.reset_paper_trading(self.starting_balance)
        self.realized_pnl = 0.0
        self.positions.clear()
        self.orders.clear()
        self.orders_changed.emit()
        self.position_changed.emit()
        self.account_changed.emit()
