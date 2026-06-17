"""
分析引擎主编排
"""
import json
from datetime import datetime
from typing import Optional

from loguru import logger

from analytics.delta_engine import run_delta_engine
from analytics.jaccard import run_jaccard
from analytics.sector_weights import run_sector_weights
from analytics.consensus import write_consensus_to_db
from db.engine import get_session
from db.models import EtlRun


def _log_analytics_run(summary: dict, status: str, error_message: Optional[str] = None, quarter: Optional[str] = None):
    try:
        with get_session() as session:
            run = EtlRun(
                run_type="analytics",
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                status=status,
                meta=json.dumps({"quarter": quarter, **summary}, ensure_ascii=False) if summary else None,
                error_message=error_message,
            )
            session.add(run)
    except Exception as e:
        logger.warning(f"Failed to log analytics run: {e}")


def run_analytics(quarter: Optional[str] = None):
    """
    运行完整分析流程
    :param quarter: 指定季度，None 则自动检测最新可用季度
    """
    logger.info("=" * 50)
    logger.info("Starting Analytics Engine")
    logger.info("=" * 50)

    summary = {"deltas": 0, "overlaps": 0, "sector_weights": 0, "consensus": 0}
    error_message = None
    status = "success"

    try:
        # 1. Delta Engine
        logger.info("Step 1: Computing holding deltas...")
        delta_count = run_delta_engine()
        summary["deltas"] = delta_count

        # 2. Jaccard
        logger.info("Step 2: Computing fund overlaps (Jaccard)...")
        jaccard_count = run_jaccard(quarter=quarter)
        summary["overlaps"] = jaccard_count

        # 3. Sector Weights
        logger.info("Step 3: Computing sector weights...")
        sector_count = run_sector_weights(quarter=quarter)
        summary["sector_weights"] = sector_count

        # 4. Consensus signals (依赖 holding_deltas，必须在 delta_engine 之后)
        logger.info("Step 4: Computing consensus signals...")
        try:
            consensus_count = write_consensus_to_db(quarter=quarter)
            summary["consensus"] = consensus_count
        except Exception as e:
            logger.error(f"Consensus computation failed: {e}")
            error_message = f"consensus: {e}"
            status = "partial"
    except Exception as e:
        logger.exception("Analytics engine failed")
        error_message = str(e)
        status = "failed"

    logger.info("=" * 50)
    logger.info("Analytics Engine Complete")
    logger.info(f"  Deltas: {summary['deltas']}")
    logger.info(f"  Overlaps: {summary['overlaps']}")
    logger.info(f"  Sector weights: {summary['sector_weights']}")
    logger.info(f"  Consensus signals: {summary['consensus']}")
    logger.info("=" * 50)

    _log_analytics_run(summary, status, error_message=error_message, quarter=quarter)

    return summary
