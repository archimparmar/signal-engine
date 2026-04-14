"""Orchestrator — ties data → signal → execution → portfolio together."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from core.data_handler import DataHandler, MockDataSource, YFinanceDataSource
from core.execution_engine import (
    ExecutionEngine,
    PercentageCommission,
    PercentageSlippage,
)
from core.models import OHLC, Order, Signal
from core.portfolio import Portfolio
from core.signal_engine import SignalEngine
from strategies.sma_crossover import SMACrossoverStrategy
from utils.logger import setup_logger

logger = setup_logger("engine")


# ── Config Loader ──────────────────────────────────────────────────────────


def load_config(path: str = "config/strategy_config.yaml") -> Dict:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f)
    logger.warning(f"Config {path} not found, using defaults")
    return {}


# ── Engine ─────────────────────────────────────────────────────────────────


class TradingEngine:
    """End-to-end backtest or streaming simulation engine."""

    def __init__(self, config: Optional[Dict] = None, user_id: str = "default"):
        self.config = config or load_config()
        self._user_id = user_id  # <-- ADDED: store user_id
        self._build_components()
        self.all_signals: List[Signal] = []
        self.all_orders: List[Order] = []

    # ── Component Factory ──────────────────────────────────────────────

    def _build_components(self) -> None:
        cfg = self.config

        # Data source
        src_cfg = cfg.get("data", {})
        if src_cfg.get("source") == "yfinance":
            source = YFinanceDataSource()
        else:
            mock_cfg = src_cfg.get("mock", {})
            source = MockDataSource(
                base_price=mock_cfg.get("base_price", 100.0),
                volatility=mock_cfg.get("volatility", 0.02),
                seed=mock_cfg.get("seed"),
            )
        self.data_handler = DataHandler(source)

        # Strategy
        strat_cfg = cfg.get("strategy", {})
        params = strat_cfg.get("params", {})
        if strat_cfg.get("name") == "sma_crossover":
            self.strategy = SMACrossoverStrategy(
                short_period=params.get("short_period", 10),
                long_period=params.get("long_period", 30),
            )
        else:
            self.strategy = SMACrossoverStrategy()

        # Signal engine
        self.signal_engine = SignalEngine()
        self.signal_engine.register_strategy(self.strategy)

        # Execution
        exec_cfg = cfg.get("execution", {})
        self.quantity = exec_cfg.get("quantity", 100)
        self.execution_engine = ExecutionEngine(
            slippage_model=PercentageSlippage(exec_cfg.get("slippage_pct", 0.001)),
            commission_model=PercentageCommission(
                exec_cfg.get("commission_pct", 0.001)
            ),
        )

        # Portfolio
        port_cfg = cfg.get("portfolio", {})
        self.portfolio = Portfolio(
            initial_cash=port_cfg.get("initial_cash", 100_000),
            user_id=self._user_id,  # <-- FIXED: use self._user_id instead of hardcoding "default"
        )

    # ── Backtest ───────────────────────────────────────────────────────

    async def run_backtest(self) -> Dict:
        """Run a full historical backtest."""
        data_cfg = self.config.get("data", {})
        symbol = data_cfg.get("symbol", "AAPL")
        start = datetime.fromisoformat(data_cfg.get("start_date", "2024-01-01"))
        end = datetime.fromisoformat(data_cfg.get("end_date", "2024-12-31"))
        interval = data_cfg.get("interval", "1d")

        logger.info("=" * 60)
        logger.info("BACKTEST START")
        logger.info(f"  User:     {self._user_id}")
        logger.info(f"  Symbol:   {symbol}")
        logger.info(f"  Period:   {start.date()} → {end.date()}")
        logger.info(f"  Strategy: {self.strategy.name}")
        logger.info(f"  Cash:     {self.portfolio.initial_cash:,.2f}")
        logger.info("=" * 60)

        # 1) Fetch data
        data = await self.data_handler.get_data(symbol, start, end, interval)
        if not data:
            logger.error("No data fetched — aborting")
            return {}

        # 2) Generate signals
        signals_map = self.signal_engine.generate_signals(data, self.strategy.name)
        signals = signals_map.get(self.strategy.name, [])
        self.all_signals = signals

        # 3) Walk forward: execute signals with look-ahead-free logic
        #    We execute at the *next* bar's open price for realism.
        signal_idx = 0
        for i in range(1, len(data)):
            bar = data[i]
            # Update market prices for unrealized PnL
            self.portfolio.update_market_prices({symbol: bar.close})

            # Execute any signal whose timestamp matches the previous bar
            while (
                signal_idx < len(signals)
                and signals[signal_idx].timestamp <= data[i - 1].timestamp
            ):
                sig = signals[signal_idx]
                # Execute at current bar's open (realistic: you see signal, act next bar)
                order = self.execution_engine.execute_signal(
                    sig, self.quantity, market_price=bar.open
                )
                if order:
                    self.all_orders.append(order)
                    self.portfolio.process_order(order)
                signal_idx += 1

        # Close any remaining open positions at last close
        last_price = data[-1].close
        for sym in list(self.portfolio.positions.keys()):
            from core.models import Order as O, OrderSide as OS, OrderStatus as OSt

            pos = self.portfolio.positions[sym]
            close_order = O(
                order_id=self.execution_engine._next_id(),
                timestamp=data[-1].timestamp,
                symbol=sym,
                side=OS.SELL,
                quantity=pos.quantity,
                price=last_price,
                status=OSt.PENDING,
            )
            close_order = self.execution_engine.execute_order(close_order, last_price)
            self.all_orders.append(close_order)
            self.portfolio.process_order(close_order)

        # Final snapshot
        snap = self.portfolio.take_snapshot(data[-1].timestamp)

        logger.info("=" * 60)
        logger.info("BACKTEST COMPLETE")
        summary = self.portfolio.get_summary()
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")
        logger.info("=" * 60)

        return summary

    # ── Streaming Simulation ───────────────────────────────────────────

    async def run_streaming(self, max_bars: int = 50) -> None:
        """Simulate a real-time stream: one bar at a time with async delay."""
        data_cfg = self.config.get("data", {})
        symbol = data_cfg.get("symbol", "AAPL")
        sim_cfg = self.config.get("simulation", {})
        delay = sim_cfg.get("stream_delay_seconds", 1)
        max_bars = max_bars or sim_cfg.get("max_bars", 500)

        logger.info("=" * 60)
        logger.info(f"STREAMING START — {symbol} (max {max_bars} bars)")
        logger.info("=" * 60)

        bar_buffer: List[OHLC] = []
        count = 0

        async for bar in self.data_handler.stream_data(symbol):
            bar_buffer.append(bar)
            count += 1

            # Update prices
            self.portfolio.update_market_prices({symbol: bar.close})

            # Need enough bars for the long SMA
            if len(bar_buffer) >= self.strategy.long_period + 1:
                signals = self.strategy.generate_signals(bar_buffer)
                for sig in signals:
                    if sig.timestamp == bar.timestamp:
                        order = self.execution_engine.execute_signal(
                            sig, self.quantity, market_price=bar.close
                        )
                        if order:
                            self.all_orders.append(order)
                            self.portfolio.process_order(order)

            snap = self.portfolio.take_snapshot(bar.timestamp)
            logger.info(
                f"[{count:04d}] {bar.timestamp.strftime('%H:%M:%S')} "
                f"O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} | "
                f"Val={snap.total_value:,.2f} PnL={snap.unrealized_pnl:+,.2f}"
            )

            if count >= max_bars:
                break

        logger.info("STREAMING ENDED")
        summary = self.portfolio.get_summary()
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")


# ── Multi-User Portfolio Manager ───────────────────────────────────────────


class PortfolioManager:
    """Manages per-user Portfolio instances — foundation for multi-tenant use."""

    def __init__(self):
        self._portfolios: Dict[str, Portfolio] = {}

    def get(self, user_id: str, initial_cash: float = 100_000) -> Portfolio:
        if user_id not in self._portfolios:
            self._portfolios[user_id] = Portfolio(initial_cash, user_id)
        return self._portfolios[user_id]

    def list_users(self) -> List[str]:
        return list(self._portfolios.keys())

    def get_all_summaries(self) -> Dict[str, Dict]:
        return {uid: p.get_summary() for uid, p in self._portfolios.items()}
