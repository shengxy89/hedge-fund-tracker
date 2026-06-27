#!/usr/bin/env python3
"""
历史数据回填脚本
支持真实 API 抓取和模拟数据两种模式
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from etl.mock_data import seed_mock_data
from etl.pipeline import run_etl_pipeline


def backfill(quarters: int = 8, use_mock: bool = False):
    """回填最近 quarters 个季度的数据"""
    if use_mock:
        logger.info("Running backfill with MOCK data...")
        asyncio.run(seed_mock_data(quarters))
        logger.info("[OK] Mock backfill complete.")
    else:
        logger.info("Running backfill with REAL API data...")
        summary = asyncio.run(run_etl_pipeline(quarters=quarters))
        logger.info(f"[OK] Real backfill complete. Summary: {summary}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="13F Backfill Script")
    parser.add_argument("--quarters", type=int, default=8, help="Number of quarters to backfill")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of real API")
    args = parser.parse_args()
    backfill(quarters=args.quarters, use_mock=args.mock)
