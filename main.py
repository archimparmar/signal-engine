"""CLI entry point — run backtest or streaming simulation."""

import asyncio
import argparse
import json

from engine import TradingEngine, load_config
from utils.logger import setup_logger

logger = setup_logger("main")


def main():
    parser = argparse.ArgumentParser(description="Signal Engine CLI")
    parser.add_argument(
        "mode",
        choices=["backtest", "stream"],
        help="Run mode: backtest or stream",
    )
    parser.add_argument(
        "--config", default="config/strategy_config.yaml", help="Config file path"
    )
    parser.add_argument("--symbol", default=None, help="Override symbol")
    parser.add_argument("--short", type=int, default=None, help="Short SMA period")
    parser.add_argument("--long", type=int, default=None, help="Long SMA period")
    parser.add_argument("--cash", type=float, default=None, help="Initial cash")
    parser.add_argument(
        "--max-bars", type=int, default=None, help="Max bars for streaming"
    )
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI overrides
    if args.symbol:
        config.setdefault("data", {})["symbol"] = args.symbol
    if args.short:
        config.setdefault("strategy", {}).setdefault("params", {})[
            "short_period"
        ] = args.short
    if args.long:
        config.setdefault("strategy", {}).setdefault("params", {})[
            "long_period"
        ] = args.long
    if args.cash:
        config.setdefault("portfolio", {})["initial_cash"] = args.cash
    if args.max_bars:
        config.setdefault("simulation", {})["max_bars"] = args.max_bars

    engine = TradingEngine(config)

    if args.mode == "backtest":
        result = asyncio.run(engine.run_backtest())
        print("\n📊  BACKTEST RESULT")
        print(json.dumps(result, indent=2))
    else:
        max_bars = config.get("simulation", {}).get("max_bars", 50)
        asyncio.run(engine.run_streaming(max_bars=max_bars))


if __name__ == "__main__":
    main()
