"""
分析引擎主编排
"""
from typing import Optional

from loguru import logger

from analytics.delta_engine import run_delta_engine
from analytics.jaccard import run_jaccard
from analytics.sector_weights import run_sector_weights


def run_analytics(quarter: Optional[str] = None):
    """
    运行完整分析流程
    :param quarter: 指定季度，None 则自动检测最新可用季度
    """
    logger.info("=" * 50)
    logger.info("Starting Analytics Engine")
    logger.info("=" * 50)

    # 1. Delta Engine
    logger.info("Step 1: Computing holding deltas...")
    delta_count = run_delta_engine()

    # 2. Jaccard
    logger.info("Step 2: Computing fund overlaps (Jaccard)...")
    jaccard_count = run_jaccard(quarter=quarter)

    # 3. Sector Weights
    logger.info("Step 3: Computing sector weights...")
    sector_count = run_sector_weights(quarter=quarter)

    logger.info("=" * 50)
    logger.info("Analytics Engine Complete")
    logger.info(f"  Deltas: {delta_count}")
    logger.info(f"  Overlaps: {jaccard_count}")
    logger.info(f"  Sector weights: {sector_count}")
    logger.info("=" * 50)

    return {
        "deltas": delta_count,
        "overlaps": jaccard_count,
        "sector_weights": sector_count,
    }
