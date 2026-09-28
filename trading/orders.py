"""Order model and fill logic for the paper-trading simulator.

Orders are matched against the live price feed. Fill rules:
  market      -> fills immediately at current price
  limit  buy  -> fills when price <= limit ; sell -> price >= limit
  stop   buy  -> triggers when price >= stop ; sell -> price <= stop (fills market)
  stop_limit  -> once the stop triggers it behaves like a limit at limit_price
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

BUY = "buy"
SELL = "sell"

MARKET = "market"
LIMIT = "limit"
STOP = "stop"
STOP_LIMIT = "stop_limit"

OPEN = "open"
FILLED = "filled"
CANCELLED = "cancelled"


@dataclass
class Order:
    ticker: str
    side: str
    type: str
    qty: float
    limit_price: float | None = None
    stop_price: float | None = None
    status: str = OPEN
    id: int | None = None
    created_at: float = field(default_factory=time.time)
    filled_at: float | None = None
    fill_price: float | None = None
    _stop_triggered: bool = False

    def to_db(self) -> dict:
        return {
            "ticker": self.ticker, "side": self.side, "type": self.type,
            "qty": self.qty, "limit_price": self.limit_price,
            "stop_price": self.stop_price, "status": self.status,
            "created_at": self.created_at, "filled_at": self.filled_at,
            "fill_price": self.fill_price,
        }

    @classmethod
    def from_db(cls, row: dict) -> "Order":
        return cls(
            ticker=row["ticker"], side=row["side"], type=row["type"],
            qty=row["qty"], limit_price=row["limit_price"],
            stop_price=row["stop_price"], status=row["status"], id=row["id"],
            created_at=row["created_at"], filled_at=row["filled_at"],
            fill_price=row["fill_price"],
        )

    def check_fill(self, price: float) -> float | None:
        """Return a fill price if this order should fill at ``price``, else None."""
        if self.status != OPEN:
            return None
        if self.type == MARKET:
            return price
        if self.type == LIMIT:
            if self.side == BUY and price <= self.limit_price:
                return self.limit_price
            if self.side == SELL and price >= self.limit_price:
                return self.limit_price
            return None
        if self.type == STOP:
            if self.side == BUY and price >= self.stop_price:
                return price
            if self.side == SELL and price <= self.stop_price:
                return price
            return None
        if self.type == STOP_LIMIT:
            if not self._stop_triggered:
                if (self.side == BUY and price >= self.stop_price) or \
                   (self.side == SELL and price <= self.stop_price):
                    self._stop_triggered = True
            if self._stop_triggered:
                if self.side == BUY and price <= self.limit_price:
                    return self.limit_price
                if self.side == SELL and price >= self.limit_price:
                    return self.limit_price
            return None
        return None

    def describe(self) -> str:
        bits = [self.side.upper(), self.type.replace("_", "-").upper(),
                f"x{self.qty:g}"]
        if self.limit_price:
            bits.append(f"@{self.limit_price:.2f}")
        if self.stop_price:
            bits.append(f"stop {self.stop_price:.2f}")
        return " ".join(bits)
