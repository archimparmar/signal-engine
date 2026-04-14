"""Execution engine — order creation, slippage, commission simulation."""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from core.models import Order, OrderSide, OrderStatus, Signal, SignalType

logger = logging.getLogger(__name__)


# ── Slippage Models ───────────────────────────────────────────────────────


class SlippageModel(ABC):
    @abstractmethod
    def calculate(self, price: float, side: OrderSide) -> float: ...


class ZeroSlippage(SlippageModel):
    def calculate(self, price: float, side: OrderSide) -> float:
        return 0.0


class PercentageSlippage(SlippageModel):
    def __init__(self, pct: float = 0.001):
        self.pct = pct

    def calculate(self, price: float, side: OrderSide) -> float:
        slip = price * self.pct
        return slip if side == OrderSide.BUY else -slip


# ── Commission Models ─────────────────────────────────────────────────────


class CommissionModel(ABC):
    @abstractmethod
    def calculate(self, price: float, quantity: float) -> float: ...


class ZeroCommission(CommissionModel):
    def calculate(self, price: float, quantity: float) -> float:
        return 0.0


class PercentageCommission(CommissionModel):
    def __init__(self, pct: float = 0.001):
        self.pct = pct

    def calculate(self, price: float, quantity: float) -> float:
        return price * quantity * self.pct


class FixedCommission(CommissionModel):
    def __init__(self, amount: float = 1.0):
        self.amount = amount

    def calculate(self, price: float, quantity: float) -> float:
        return self.amount


# ── Execution Engine ──────────────────────────────────────────────────────


class ExecutionEngine:
    """Converts signals → orders → fills with slippage & commission."""

    def __init__(
        self,
        slippage_model: Optional[SlippageModel] = None,
        commission_model: Optional[CommissionModel] = None,
    ):
        self.slippage_model = slippage_model or PercentageSlippage(0.001)
        self.commission_model = commission_model or PercentageCommission(0.001)
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"ORD-{self._seq:06d}-{uuid.uuid4().hex[:6]}"

    # ── Public API ─────────────────────────────────────────────────────

    def signal_to_order(self, signal: Signal, quantity: float) -> Optional[Order]:
        if signal.signal_type == SignalType.HOLD:
            return None

        side = OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL
        order = Order(
            order_id=self._next_id(),
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=signal.price,
        )
        logger.info(
            f"Order created: {order.order_id} {side.value} {quantity} {signal.symbol} @ {signal.price}"
        )
        return order

    def execute_order(
        self, order: Order, market_price: Optional[float] = None
    ) -> Order:
        base = market_price or order.price
        slip = self.slippage_model.calculate(base, order.side)
        filled = round(base + slip, 4)
        commission = round(self.commission_model.calculate(filled, order.quantity), 4)

        order.filled_price = filled
        order.filled_timestamp = datetime.now()
        order.status = OrderStatus.FILLED
        order.commission = commission
        order.slippage = round(slip, 4)

        logger.info(
            f"Filled {order.order_id}: {order.side.value} {order.quantity} "
            f"{order.symbol} @ {filled} (slip={slip:.4f}, comm={commission:.2f})"
        )
        return order

    def execute_signal(
        self,
        signal: Signal,
        quantity: float,
        market_price: Optional[float] = None,
    ) -> Optional[Order]:
        """One-call convenience: signal → order → fill."""
        order = self.signal_to_order(signal, quantity)
        if order is None:
            return None
        return self.execute_order(order, market_price or signal.price)
