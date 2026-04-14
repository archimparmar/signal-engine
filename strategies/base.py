"""Abstract interfaces for indicators and strategies."""

from abc import ABC, abstractmethod
from typing import List

from core.models import OHLC, Signal


class Indicator(ABC):
    """Computes a numeric series from OHLC data."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def compute(self, data: List[OHLC]) -> List[float | None]: ...


class Strategy(ABC):
    """Consumes OHLC data, emits Signals."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def required_indicators(self) -> List[Indicator]: ...

    @abstractmethod
    def generate_signals(self, data: List[OHLC]) -> List[Signal]: ...
