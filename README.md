Signal Engine
A modular, extensible data-processing and signal-generation backend built in Python. Ingests OHLC data, computes technical indicators, generates trading signals, simulates execution with slippage/commission, and tracks portfolio performance.

Architecture
The system follows a strict layered architecture where data flows directionally through distinct components with clear separation of concerns.

## Project Structure

signal_engine/
├── core/ # Domain layer — models + engines
│ ├── models.py # Pure dataclasses (OHLC, Signal, Order, Position, Trade)
│ ├── data_handler.py # Ingestion: DataSource ABC, Mock, YFinance, DataHandler
│ ├── signal_engine.py # Strategy registry + signal generation
│ ├── execution_engine.py # Order fill simulation (slippage + commission)
│ └── portfolio.py # Position tracking, PnL, trade history
├── strategies/ # Plug-in strategies & indicators
│ ├── base.py # Indicator & Strategy ABCs
│ └── sma_crossover.py # SMA crossover (with SMA & EMA indicators)
├── config/
│ └── strategy_config.yaml # Config-driven parameters
├── api/
│ └── main.py # FastAPI REST layer (multi-user)
├── utils/
│ └── logger.py # Structured logging setup
├── engine.py # Orchestrator: backtest + streaming + PortfolioManager
├── main.py # CLI entry point
├── requirements.txt
└── README.md

text


---

## Requirements Satisfaction

### Core Requirements
1. **Data Ingestion Layer**: Extensible `DataSource` ABC with `MockDataSource` and `YFinanceDataSource`. Caching handled by `DataHandler`.
2. **Processing Engine**: `Strategy` and `Indicator` ABCs. Implemented `SimpleMovingAverage` and `SMACrossoverStrategy`. 
3. **Execution Engine**: `ExecutionEngine` converts Signals to Orders and simulates fills with configurable `SlippageModel` and `CommissionModel`.
4. **Portfolio Tracking**: `Portfolio` class tracks cash, open positions, mark-to-market unrealized PnL, realized PnL, and full trade history.
5. **System Design**: Code is modularized into `core/`, `strategies/`, `api/`, and `utils/` exactly as requested.
6. **Real-Time Simulation**: Async streaming via `async for` loop in `DataHandler.stream_data()`, processed bar-by-bar in `TradingEngine.run_streaming()`.
7. **Output**: Structured logging outputs signals, order fills, trades, and final PnL summary to console.

### Bonus Requirements
- **Async/Threading**: Data ingestion is fully `async`. `yfinance` downloads run in a thread executor (`run_in_executor`). Streaming uses `asyncio.sleep`.
- **Config-driven strategy**: Strategy parameters (SMA periods), data sources, execution costs, and initial cash are driven by `strategy_config.yaml`. CLI and API payloads can override these at runtime.
- **Multi-user design**: `PortfolioManager` isolates `Portfolio` instances by `user_id`. FastAPI routes (`/portfolio/{user_id}`) allow multiple users to run isolated backtests simultaneously.
- **Simple API (FastAPI)**: Fully functional REST API with auto-generated Swagger docs at `/docs`.

---

## Design Decisions

### 1. Extensibility via Abstract Base Classes (ABCs)
The system relies heavily on ABCs (`DataSource`, `Indicator`, `Strategy`, `SlippageModel`, `CommissionModel`). This ensures the core engine is closed for modification but open for extension. Adding a new data source (e.g., Alpaca, Binance) or a new strategy (e.g., RSI, MACD) requires zero changes to the core engine—just implement the interface.

### 2. Look-Ahead-Free Backtesting
To prevent unrealistic backtest results, the `TradingEngine` executes signals at the *next* bar's open price. If a signal is generated at Bar T, the order is filled at Bar T+1's open price, mimicking real-world latency.

### 3. Config-Driven Flexibility
All tunable parameters live in `config/strategy_config.yaml`. The `TradingEngine` reads this at initialization, but the FastAPI layer and CLI can override these configurations dynamically per request, allowing parameter sweeps without code changes.

### 4. Domain Model Purity
The `core/models.py` file contains pure Python dataclasses with zero external dependencies. This keeps the domain layer lightweight, serializable, and easy to test, while heavier dependencies (like `pandas` or `yfinance`) are isolated to the boundaries (data ingestion).

---

## Quick Start

### Installation

```bash
git clone <your-repo-url>
cd signal_engine
pip install -r requirements.txt
CLI Usage
Run a historical backtest:

bash

python main.py backtest --symbol AAPL --short 10 --long 30 --cash 100000
Run a streaming simulation:

bash

python main.py stream --symbol AAPL --max-bars 100
API Usage
Start the API server:

bash

uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
Interactive Swagger Docs:
Open your browser and navigate to http://localhost:8000/docs

API Endpoints:

Method
Endpoint
Description
GET	/health	Health check
POST	/backtest	Run historical backtest for a user
POST	/stream/start	Start streaming simulation for a user
POST	/stream/stop	Stop streaming simulation
GET	/portfolio/{user_id}	Portfolio summary (cash, PnL, etc.)
GET	/portfolio/{user_id}/positions	Open positions
GET	/portfolio/{user_id}/trades	Trade history
GET	/users	List all user IDs
GET	/strategies	List registered strategies

Example API Call (Windows CMD):

cmd

curl -X POST http://localhost:8000/backtest -H "Content-Type: application/json" -d "{\"user_id\":\"alice\",\"symbol\":\"AAPL\",\"start_date\":\"2024-01-01\",\"end_date\":\"2024-12-31\",\"short_period\":10,\"long_period\":30}"
Example API Call (Linux/Mac):

bash

curl -X POST http://localhost:8000/backtest \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","symbol":"AAPL","start_date":"2024-01-01","end_date":"2024-12-31","short_period":10,"long_period":30}'
Scaling Approach
The current architecture is designed for local simulation and single-instance deployment. Here is the path to production scalability:

Concern
Current Implementation
Production Scaling Path
Data Storage	In-memory caching / pandas DataFrames	TimescaleDB / InfluxDB: Migrate OHLC data to time-series databases for fast range queries. Use Redis for real-time tick caching.
Multi-User Isolation	PortfolioManager dict in process memory	PostgreSQL + SQLAlchemy: Persist user state, positions, and trades to a relational DB with row-level locking for concurrent user actions.
Real-Time Streaming	asyncio.sleep loop per user	WebSocket + Kafka/Redis Streams: Users connect via WebSocket. Market data is published to Kafka topics; strategy workers consume and publish signal events.
Computation	Single-threaded async loop	Celery / Dask: Offload heavy backtests and indicator computations to distributed task queues to keep the API layer responsive.
Strategy Deployment	Static code import	Plugin System: Use importlib to dynamically load strategy classes from a defined directory or S3 bucket without restarting the API.
Authentication	None	JWT / OAuth2: Add FastAPI middleware to secure endpoints and map auth users to user_id in PortfolioManager.
```		