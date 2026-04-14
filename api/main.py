"""FastAPI application — REST endpoints for the signal engine."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from engine import TradingEngine, PortfolioManager, load_config
from core.models import SignalType

app = FastAPI(
    title="Signal Engine API",
    description="Data processing & signal engine with backtest and streaming",
    version="1.0.0",
)

# ── Global State ───────────────────────────────────────────────────────────

portfolio_mgr = PortfolioManager()
_engines: Dict[str, TradingEngine] = {}
_streaming_tasks: Dict[str, asyncio.Task] = {}


def _engine(user_id: str) -> TradingEngine:
    if user_id not in _engines:
        # FIXED: Pass user_id into TradingEngine
        _engines[user_id] = TradingEngine(load_config(), user_id=user_id)
        _engines[user_id].portfolio = portfolio_mgr.get(user_id)
    return _engines[user_id]


# ── Request / Response Models ──────────────────────────────────────────────


class BacktestRequest(BaseModel):
    user_id: str = "default"
    symbol: str = "AAPL"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    short_period: int = 10
    long_period: int = 30
    initial_cash: float = 100_000


class StreamRequest(BaseModel):
    user_id: str = "default"
    symbol: str = "AAPL"
    max_bars: int = 50


class PortfolioResponse(BaseModel):
    user_id: str
    initial_cash: float
    current_cash: float
    positions_value: float
    total_value: float
    total_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    total_commission: float
    open_positions: int
    total_trades: int
    win_rate: float


# ── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/backtest", response_model=Dict)
async def run_backtest(req: BacktestRequest):
    """Run a historical backtest for a user."""
    config = load_config()
    config["data"]["symbol"] = req.symbol
    config["data"]["start_date"] = req.start_date
    config["data"]["end_date"] = req.end_date
    config["strategy"]["params"]["short_period"] = req.short_period
    config["strategy"]["params"]["long_period"] = req.long_period
    config["portfolio"]["initial_cash"] = req.initial_cash

    # FIXED: Pass the user_id from the request into the TradingEngine
    engine = TradingEngine(config, user_id=req.user_id)
    _engines[req.user_id] = engine
    portfolio_mgr._portfolios[req.user_id] = engine.portfolio

    result = await engine.run_backtest()
    return result


@app.post("/stream/start", response_model=Dict)
async def start_stream(req: StreamRequest, bg: BackgroundTasks):
    """Start a streaming simulation in the background."""
    if req.user_id in _streaming_tasks:
        return {"status": "already_running", "user_id": req.user_id}

    engine = _engine(req.user_id)

    async def _run():
        await engine.run_streaming(max_bars=req.max_bars)
        _streaming_tasks.pop(req.user_id, None)

    task = asyncio.create_task(_run())
    _streaming_tasks[req.user_id] = task
    return {"status": "started", "user_id": req.user_id}


@app.post("/stream/stop", response_model=Dict)
async def stop_stream(user_id: str = "default"):
    task = _streaming_tasks.pop(user_id, None)
    if task:
        task.cancel()
        return {"status": "stopped", "user_id": user_id}
    return {"status": "not_running", "user_id": user_id}


@app.get("/portfolio/{user_id}", response_model=Dict)
async def get_portfolio(user_id: str):
    port = portfolio_mgr.get(user_id)
    return port.get_summary()


@app.get("/portfolio/{user_id}/positions", response_model=List[Dict])
async def get_positions(user_id: str):
    port = portfolio_mgr.get(user_id)
    return port.get_position_details()


@app.get("/portfolio/{user_id}/trades", response_model=List[Dict])
async def get_trades(user_id: str):
    port = portfolio_mgr.get(user_id)
    return port.get_trade_history()


@app.get("/users", response_model=List[str])
async def list_users():
    return portfolio_mgr.list_users()


@app.get("/strategies", response_model=List[str])
async def list_strategies(user_id: str = "default"):
    eng = _engine(user_id)
    return eng.signal_engine.list_strategies()


# ── Entry ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
