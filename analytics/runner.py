"""
分析引擎主编排
"""
import json
from datetime import datetime

from loguru import logger

from analytics.concentration import run_concentration
from analytics.consensus import write_consensus_to_db
from analytics.delta_engine import run_delta_engine
from analytics.jaccard import run_jaccard
from analytics.sector_weights import run_sector_weights
from db.engine import get_session
from db.models import EtlRun


def _log_analytics_run(summary: dict, status: str, error_message: str | None = None, quarter: str | None = None):
    """记录分析运行到 etl_runs 表。"""
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


def run_analytics(quarter: str | None = None):
    """
    运行完整分析流程
    :param quarter: 指定季度，None 则自动检测最新可用季度
    """
    logger.info("=" * 50)
    logger.info("Starting Analytics Engine")
    logger.info("=" * 50)

    summary = {
        "deltas": 0,
        "consensus": 0,
        "overlaps": 0,
        "sector_weights": 0,
        "concentration": 0,
        "concentration_error": None,
    }
    error_message = None
    status = "success"

    try:
        # 1. Delta Engine
        logger.info("Step 1: Computing holding deltas...")
        summary["deltas"] = run_delta_engine()

        # 2. Consensus（核心功能，依赖 holding_deltas，必须在 delta_engine 之后）
        logger.info("Step 2: Computing consensus signals...")
        try:
            summary["consensus"] = write_consensus_to_db(quarter=quarter)
        except Exception as e:
            logger.error(f"Consensus computation failed: {e}")
            error_message = f"consensus: {e}"
            status = "partial"

        # 3. Jaccard
        logger.info("Step 3: Computing fund overlaps (Jaccard)...")
        summary["overlaps"] = run_jaccard(quarter=quarter)

        # 4. Sector Weights
        logger.info("Step 4: Computing sector weights...")
        summary["sector_weights"] = run_sector_weights(quarter=quarter)

        # 5. Concentration（非核心，允许失败并记录到返回结构）
        logger.info("Step 5: Computing fund concentration...")
        try:
            summary["concentration"] = run_concentration(quarter=quarter)
        except Exception as e:
            logger.warning(f"Concentration computation failed: {e}")
            summary["concentration_error"] = str(e)
            if status == "success":
                status = "partial"
    except Exception as e:
        logger.exception("Analytics engine failed")
        error_message = str(e)
        status = "failed"

    logger.info("=" * 50)
    logger.info("Analytics Engine Complete")
    logger.info(f"  Deltas: {summary['deltas']}")
    logger.info(f"  Consensus: {summary['consensus']}")
    logger.info(f"  Overlaps: {summary['overlaps']}")
    logger.info(f"  Sector weights: {summary['sector_weights']}")
    logger.info(f"  Concentration: {summary['concentration']}")
    logger.info("=" * 50)

    _log_analytics_run(summary, status, error_message=error_message, quarter=quarter)

    return summary
