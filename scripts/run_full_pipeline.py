#!/usr/bin/env python3
"""
一键运行脚本：初始化 -> 导入基金 -> ETL -> 分析
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

import config.logging  # noqa: F401
from db.engine import engine
from db.models import Base
from scripts.backfill import backfill
from scripts.seed_funds import seed_funds


def run_full_pipeline(mock: bool = False):
    logger.info("=" * 50)
    logger.info("Starting Full Pipeline")
    logger.info("=" * 50)

    # 1. 初始化数据库
    logger.info("Step 1: Initialize database...")
    Base.metadata.create_all(bind=engine)
    logger.info("[OK] Database initialized.")

    # 2. 导入基金清单
    logger.info("Step 2: Seed funds...")
    seed_funds()

    # 3. 回填数据
    logger.info("Step 3: Backfill holdings data...")
    backfill(quarters=8, use_mock=mock)

    logger.info("=" * 50)
    logger.info("Full pipeline complete!")
    logger.info("=" * 50)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Full 13F Pipeline")
    parser.add_argument("--mock", action="store_true", help="Use mock data for demonstration")
    args = parser.parse_args()
    run_full_pipeline(mock=args.mock)
