"""SMA Crossover strategy — the classic trend-following signal."""

import logging
from typing import List, Optional

from core.models import OHLC, Signal, SignalType
from strategies.base import Indicator, Strategy

logger = logging.getLogger(__name__)


# ── Indicators ─────────────────────────────────────────────────────────────


class SimpleMovingAverage(Indicator):
    def __init__(self, period: int):
        self.period = period

    @property
    def name(self) -> str:
        return f"SMA_{self.period}"

    def compute(self, data: List[OHLC]) -> List[Optional[float]]:
        closes = [bar.close for bar in data]
        out: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < self.period - 1:
                out.append(None)
            else:
                window = closes[i - self.period + 1 : i + 1]
                out.append(sum(window) / self.period)
        return out


class ExponentialMovingAverage(Indicator):
    def __init__(self, period: int):
        self.period = period
        self._k = 2 / (period + 1)

    @property
    def name(self) -> str:
        return f"EMA_{self.period}"

    def compute(self, data: List[OHLC]) -> List[Optional[float]]:
        closes = [bar.close for bar in data]
        out: List[Optional[float]] = []
        for i in range(len(closes)):
            if i < self.period - 1:
                out.append(None)
            elif i == self.period - 1:
                out.append(sum(closes[: self.period]) / self.period)
            else:
                out.append(closes[i] * self._k + out[-1] * (1 - self._k))
        return out


# ── Strategy ───────────────────────────────────────────────────────────────


class SMACrossoverStrategy(Strategy):
    """Buy when short SMA crosses above long SMA; sell on the reverse."""

    def __init__(self, short_period: int = 10, long_period: int = 30):
        self.short_period = short_period
        self.long_period = long_period
        self._short = SimpleMovingAverage(short_period)
        self._long = SimpleMovingAverage(long_period)

    @property
    def name(self) -> str:
        return f"SMA_Cross_{self.short_period}_{self.long_period}"

    @property
    def required_indicators(self) -> List[Indicator]:
        return [self._short, self._long]

    def generate_signals(self, data: List[OHLC]) -> List[Signal]:
        if len(data) < self.long_period + 1:
            logger.warning(
                f"{self.name}: need ≥{self.long_period + 1} bars, got {len(data)}"
            )
            return []

        short_ma = self._short.compute(data)
        long_ma = self._long.compute(data)

        signals: List[Signal] = []
        for i in range(1, len(data)):
            if None in (short_ma[i], long_ma[i], short_ma[i - 1], long_ma[i - 1]):
                continue

            prev_diff = short_ma[i - 1] - long_ma[i - 1]
            curr_diff = short_ma[i] - long_ma[i]

            signal_type = SignalType.HOLD
            if prev_diff <= 0 and curr_diff > 0:
                signal_type = SignalType.BUY
            elif prev_diff >= 0 and curr_diff < 0:
                signal_type = SignalType.SELL

            if signal_type != SignalType.HOLD:
                confidence = min(abs(curr_diff) / data[i].close * 100, 1.0)
                signals.append(
                    Signal(
                        timestamp=data[i].timestamp,
                        symbol=data[i].symbol,
                        signal_type=signal_type,
                        price=data[i].close,
                        strategy_name=self.name,
                        indicator_values={
                            self._short.name: round(short_ma[i], 4),
                            self._long.name: round(long_ma[i], 4),
                        },
                        confidence=round(confidence, 4),
                    )
                )
                logger.info(
                    f"[{self.name}] {signal_type.value} @ {data[i].timestamp.date()} "
                    f"price={data[i].close:.2f}"
                )

        logger.info(f"[{self.name}] Generated {len(signals)} signals")
        return signals
