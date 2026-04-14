"""Portfolio — position tracking, PnL accounting, trade history."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from core.models import (
    Order,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
    Position,
    PositionSide,
    Trade,
)

logger = logging.getLogger(__name__)


class Portfolio:
    """Single-user portfolio: cash, positions, trades, snapshots."""

    def __init__(self, initial_cash: float = 100_000.0, user_id: str = "default"):
        self.user_id = user_id
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self._positions: Dict[str, Position] = {}
        self._open_trades: Dict[str, Trade] = {}  # symbol → open trade
        self._closed_trades: List[Trade] = []
        self._snapshots: List[PortfolioSnapshot] = []
        self._seq = 0  # ← single counter

    # ── IDs ────────────────────────────────────────────────────────────

    def _next_trade_id(self) -> str:
        self._seq += 1
        return f"TRD-{self._seq:06d}"  # ← was self.seq — FIXED

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    @property
    def trades(self) -> List[Trade]:
        return list(self._closed_trades)

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def positions_value(self) -> float:
        return sum(p.current_price * p.quantity for p in self._positions.values())

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def total_realized_pnl(self) -> float:
        return sum(t.realized_pnl for t in self._closed_trades)

    @property
    def total_commission(self) -> float:
        all_trades = self._closed_trades + list(self._open_trades.values())
        return sum(t.commission for t in all_trades)

    @property
    def total_value(self) -> float:
        return self.cash + self.positions_value

    @property
    def total_pnl(self) -> float:
        return self.total_value - self.initial_cash

    # ── Order Processing ───────────────────────────────────────────────

    def process_order(self, order: Order) -> Optional[Trade]:
        if order.status != OrderStatus.FILLED:
            logger.warning(f"Skipping unfilled order {order.order_id}")
            return None
        if order.side == OrderSide.BUY:
            return self._process_buy(order)
        return self._process_sell(order)

    def _process_buy(self, order: Order) -> Trade:
        cost = order.filled_price * order.quantity + order.commission

        # Capital check with auto-sizing
        if cost > self.cash:
            max_qty = max(int((self.cash - order.commission) / order.filled_price), 0)
            if max_qty == 0:
                logger.error(f"Cannot afford any shares of {order.symbol}")
                return None
            logger.warning(
                f"Reduced qty {order.quantity} → {max_qty} (insufficient cash)"
            )
            order.quantity = max_qty
            cost = order.filled_price * order.quantity + order.commission

        self.cash -= cost

        if order.symbol in self._positions:
            pos = self._positions[order.symbol]
            total_qty = pos.quantity + order.quantity
            avg = (
                pos.entry_price * pos.quantity + order.filled_price * order.quantity
            ) / total_qty
            pos.entry_price = round(avg, 4)
            pos.quantity = total_qty
            pos.current_price = order.filled_price
        else:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                side=PositionSide.LONG,
                quantity=order.quantity,
                entry_price=order.filled_price,
                current_price=order.filled_price,
                timestamp=order.filled_timestamp or datetime.now(),
            )

        trade = Trade(
            trade_id=self._next_trade_id(),  # ← now correct
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=order.filled_price,
            exit_price=None,
            entry_timestamp=order.filled_timestamp or datetime.now(),
            exit_timestamp=None,
            commission=order.commission,
        )
        self._open_trades[order.symbol] = trade

        logger.info(
            f"BUY {order.quantity} {order.symbol} @ {order.filled_price} | "
            f"cash={self.cash:.2f}"
        )
        return trade

    def _process_sell(self, order: Order) -> Optional[Trade]:
        if order.symbol not in self._positions:
            logger.warning(f"No position in {order.symbol} to sell")
            return None

        pos = self._positions[order.symbol]
        if order.quantity > pos.quantity:
            order.quantity = pos.quantity

        proceeds = order.filled_price * order.quantity - order.commission
        self.cash += proceeds

        realized = (
            order.filled_price - pos.entry_price
        ) * order.quantity - order.commission

        closed = Trade(
            trade_id=self._next_trade_id(),  # ← now correct
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            entry_price=pos.entry_price,
            exit_price=order.filled_price,
            entry_timestamp=pos.timestamp,
            exit_timestamp=order.filled_timestamp or datetime.now(),
            realized_pnl=round(realized, 4),
            commission=order.commission,
        )
        self._closed_trades.append(closed)

        if order.quantity >= pos.quantity:
            del self._positions[order.symbol]
            self._open_trades.pop(order.symbol, None)
        else:
            pos.quantity -= order.quantity

        logger.info(
            f"SELL {order.quantity} {order.symbol} @ {order.filled_price} | "
            f"PnL={realized:.2f} | cash={self.cash:.2f}"
        )
        return closed

    # ── Mark-to-Market ─────────────────────────────────────────────────

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        for sym, px in prices.items():
            if sym in self._positions:
                self._positions[sym].current_price = px

    # ── Snapshots ──────────────────────────────────────────────────────

    def take_snapshot(self, timestamp: Optional[datetime] = None) -> PortfolioSnapshot:
        snap = PortfolioSnapshot(
            timestamp=timestamp or datetime.now(),
            cash=round(self.cash, 2),
            positions_value=round(self.positions_value, 2),
            total_value=round(self.total_value, 2),
            unrealized_pnl=round(self.total_unrealized_pnl, 2),
            realized_pnl=round(self.total_realized_pnl, 2),
        )
        self._snapshots.append(snap)
        return snap

    # ── Reporting ──────────────────────────────────────────────────────

    def get_summary(self) -> Dict:
        closed = self._closed_trades
        wins = sum(1 for t in closed if t.realized_pnl > 0)
        return {
            "user_id": self.user_id,
            "initial_cash": self.initial_cash,
            "current_cash": round(self.cash, 2),
            "positions_value": round(self.positions_value, 2),
            "total_value": round(self.total_value, 2),
            "total_pnl": round(self.total_pnl, 2),
            "unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "realized_pnl": round(self.total_realized_pnl, 2),
            "total_commission": round(self.total_commission, 2),
            "open_positions": len(self._positions),
            "total_trades": len(closed),
            "win_rate": round(wins / len(closed) * 100, 2) if closed else 0.0,
        }

    def get_trade_history(self) -> List[Dict]:
        return [t.to_dict() for t in self._closed_trades]

    def get_position_details(self) -> List[Dict]:
        return [p.to_dict() for p in self._positions.values()]
