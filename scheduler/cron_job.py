"""
定时任务入口
使用 schedule 库实现每日检查
"""
import time
import asyncio
from datetime import datetime

import config.logging  # noqa: F401
import schedule
from loguru import logger

from config.settings import get_settings
from db.engine import get_session
from db.models import Filing, Fund
from etl.pipeline import run_etl_pipeline
from analytics.runner import run_analytics

settings = get_settings()


def check_new_filings() -> list[str]:
    """
    检查是否有新的 13F filing
    返回有更新的基金 CIK 列表
    """
    updated_ciks = []
    with get_session() as session:
        funds = session.query(Fund).filter(Fund.is_active == True).all()
        for fund in funds:
            latest = session.query(Filing).filter(
                Filing.fund_id == fund.fund_id
            ).order_by(Filing.filing_date.desc()).first()
            # 简化：实际应调用 API 检查最新 filing_date
            # 这里仅做演示逻辑
            logger.debug(f"Checked {fund.name}, latest filing: {latest.filing_date if latest else 'None'}")
    return updated_ciks


def daily_check():
    """每日检查任务"""
    logger.info("Running daily 13F check...")
    updated_ciks = check_new_filings()
    if updated_ciks:
        logger.info(f"Found updates for {len(updated_ciks)} funds")
        summary = asyncio.run(run_etl_pipeline(fund_ciks=updated_ciks))
        run_analytics()
        logger.info(f"Update complete: {summary}")
    else:
        logger.info("No new filings found.")


def run_scheduler():
    """启动定时调度器"""
    logger.info("Starting scheduler...")
    schedule.every().day.at("06:00").do(daily_check)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
