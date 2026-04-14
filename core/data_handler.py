"""Data ingestion layer — extensible via the DataSource ABC."""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import AsyncIterator, Dict, List, Optional

from core.models import OHLC

logger = logging.getLogger(__name__)


# ── Abstract Source ────────────────────────────────────────────────────────


class DataSource(ABC):
    """Every data source must implement historical fetch + async stream."""

    @abstractmethod
    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> List[OHLC]: ...

    @abstractmethod
    async def stream(
        self, symbol: str, interval: str = "1d"
    ) -> AsyncIterator[OHLC]: ...


# ── Mock Source ────────────────────────────────────────────────────────────


class MockDataSource(DataSource):
    """Deterministic-ish random walk for local testing."""

    def __init__(
        self,
        base_price: float = 100.0,
        volatility: float = 0.02,
        seed: Optional[int] = None,
    ):
        self.base_price = base_price
        self.volatility = volatility
        if seed is not None:
            random.seed(seed)

    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> List[OHLC]:
        logger.info(f"[Mock] Fetching {symbol} {start.date()} → {end.date()}")
        bars: List[OHLC] = []
        price = self.base_price
        dt = start
        while dt <= end:
            o = price
            c = price + random.gauss(0, self.volatility * price)
            h = max(o, c) + abs(random.gauss(0, self.volatility * price * 0.3))
            l = min(o, c) - abs(random.gauss(0, self.volatility * price * 0.3))
            v = random.randint(100_000, 10_000_000)
            bars.append(
                OHLC(dt, round(o, 2), round(h, 2), round(l, 2), round(c, 2), v, symbol)
            )
            price = c
            dt += timedelta(days=1)
        logger.info(f"[Mock] Returned {len(bars)} bars")
        return bars

    async def stream(self, symbol: str, interval: str = "1d") -> AsyncIterator[OHLC]:
        price = self.base_price
        while True:
            o = price
            c = price + random.gauss(0, self.volatility * price)
            h = max(o, c) + abs(random.gauss(0, self.volatility * price * 0.3))
            l = min(o, c) - abs(random.gauss(0, self.volatility * price * 0.3))
            v = random.randint(100_000, 10_000_000)
            yield OHLC(
                datetime.now(),
                round(o, 2),
                round(h, 2),
                round(l, 2),
                round(c, 2),
                v,
                symbol,
            )
            price = c
            await asyncio.sleep(1)


# ── Yahoo Finance Source ──────────────────────────────────────────────────


class YFinanceDataSource(DataSource):
    """Live data via yfinance; download runs in a thread executor."""

    async def fetch_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> List[OHLC]:
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed — `pip install yfinance`")
            raise

        logger.info(f"[YFinance] Fetching {symbol} {start.date()} → {end.date()}")
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(
                symbol, start=start, end=end, interval=interval, progress=False
            ),
        )
        if df.empty:
            logger.warning(f"[YFinance] No data for {symbol}")
            return []

        bars: List[OHLC] = []
        for idx, row in df.iterrows():
            ts = (
                idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.now()
            )
            bars.append(
                OHLC(
                    timestamp=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    symbol=symbol,
                )
            )
        logger.info(f"[YFinance] Returned {len(bars)} bars")
        return bars

    async def stream(self, symbol: str, interval: str = "1d") -> AsyncIterator[OHLC]:
        while True:
            bars = await self.fetch_historical(
                symbol, datetime.now() - timedelta(days=5), datetime.now(), interval
            )
            if bars:
                yield bars[-1]
            await asyncio.sleep(60)


# ── Data Handler (façade) ─────────────────────────────────────────────────


class DataHandler:
    """Caching façade over any DataSource."""

    def __init__(self, source: Optional[DataSource] = None):
        self.source = source or MockDataSource()
        self._cache: Dict[str, List[OHLC]] = {}

    async def get_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
        use_cache: bool = True,
    ) -> List[OHLC]:
        key = f"{symbol}_{start.date()}_{end.date()}_{interval}"
        if use_cache and key in self._cache:
            logger.info(f"Cache hit: {key}")
            return self._cache[key]

        data = await self.source.fetch_historical(symbol, start, end, interval)
        self._cache[key] = data
        return data

    async def stream_data(
        self, symbol: str, interval: str = "1d"
    ) -> AsyncIterator[OHLC]:
        async for bar in self.source.stream(symbol, interval):
            yield bar

    def clear_cache(self) -> None:
        self._cache.clear()
