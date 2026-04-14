"""Signal engine — registry of strategies, indicator computation hub."""

import logging
from typing import Dict, List, Optional

from core.models import OHLC, Signal
from strategies.base import Indicator, Strategy

logger = logging.getLogger(__name__)


class SignalEngine:
    """Pluggable strategy registry + signal generation."""

    def __init__(self):
        self._strategies: Dict[str, Strategy] = {}
        self._indicators: Dict[str, Indicator] = {}

    # ── Registration ───────────────────────────────────────────────────

    def register_strategy(self, strategy: Strategy) -> None:
        self._strategies[strategy.name] = strategy
        for ind in strategy.required_indicators:
            self._indicators[ind.name] = ind
        logger.info(f"Registered strategy: {strategy.name}")

    def register_indicator(self, indicator: Indicator) -> None:
        self._indicators[indicator.name] = indicator
        logger.info(f"Registered indicator: {indicator.name}")

    # ── Signal Generation ──────────────────────────────────────────────

    def generate_signals(
        self,
        data: List[OHLC],
        strategy_name: Optional[str] = None,
    ) -> Dict[str, List[Signal]]:
        strategies = (
            {strategy_name: self._strategies[strategy_name]}
            if strategy_name
            else self._strategies
        )
        results: Dict[str, List[Signal]] = {}
        for name, strat in strategies.items():
            results[name] = strat.generate_signals(data)
        return results

    # ── Raw Indicator Values ───────────────────────────────────────────

    def compute_indicators(self, data: List[OHLC]) -> Dict[str, List[float | None]]:
        return {name: ind.compute(data) for name, ind in self._indicators.items()}

    # ── Listing ────────────────────────────────────────────────────────

    def list_strategies(self) -> List[str]:
        return list(self._strategies.keys())

    def list_indicators(self) -> List[str]:
        return list(self._indicators.keys())
