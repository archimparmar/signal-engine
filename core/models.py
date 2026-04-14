"""Domain models — pure dataclasses with no external dependencies."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


# ── Enums ──────────────────────────────────────────────────────────────────


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


# ── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class OHLC:
    """Single candle / bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
        }


@dataclass
class Signal:
    """Trading signal produced by a strategy."""

    timestamp: datetime
    symbol: str
    signal_type: SignalType
    price: float
    strategy_name: str = ""
    indicator_values: Dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "price": self.price,
            "strategy_name": self.strategy_name,
            "indicator_values": self.indicator_values,
            "confidence": self.confidence,
        }


@dataclass
class Order:
    """Order created from a signal, before execution."""

    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value,
            "filled_price": self.filled_price,
            "commission": self.commission,
            "slippage": self.slippage,
        }


@dataclass
class Position:
    """Open position in a symbol."""

    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    timestamp: datetime

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "market_value": round(self.market_value, 2),
        }


@dataclass
class Trade:
    """Completed (closed) trade record."""

    trade_id: str
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    entry_timestamp: datetime
    exit_timestamp: Optional[datetime]
    realized_pnl: float = 0.0
    commission: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "realized_pnl": round(self.realized_pnl, 2),
            "commission": round(self.commission, 2),
            "entry_time": self.entry_timestamp.isoformat(),
            "exit_time": (
                self.exit_timestamp.isoformat() if self.exit_timestamp else None
            ),
        }


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""

    timestamp: datetime
    cash: float
    positions_value: float
    total_value: float
    unrealized_pnl: float
    realized_pnl: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": self.cash,
            "positions_value": self.positions_value,
            "total_value": self.total_value,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
        }
