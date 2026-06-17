"""
定时任务入口
使用 schedule 库实现每日检查
"""
import time
import asyncio
from datetime import datetime, date

import config.logging  # noqa: F401
import schedule
from loguru import logger

from config.settings import get_settings
from db.engine import get_session
from db.models import Filing, Fund
from etl.fetcher import fetch_filings_sec
from etl.pipeline import run_etl_pipeline
from analytics.runner import run_analytics

settings = get_settings()


async def check_new_filings() -> list[str]:
    """检查所有 active 基金在 SEC EDGAR 上是否有比 DB 更新的 13F filing。

    Returns:
        有新 filing 的基金 CIK 列表
    """
    updated_ciks: list[str] = []

    with get_session(read_only=True) as session:
        funds = session.query(Fund).filter(Fund.is_active.is_(True)).all()
        fund_ciks = [(f.fund_id, f.cik, f.name) for f in funds]


    logger.info(f"Checking {len(fund_ciks)} active funds for new 13F filings...")

    # 顺序检查，避免触发 SEC 速率限制（RateLimiter 会自动延迟）
    for fund_id, cik, name in fund_ciks:
        try:
            with get_session(read_only=True) as session:
                latest = session.query(Filing).filter(
                    Filing.fund_id == fund_id
                ).order_by(Filing.filing_date.desc()).first()
            latest_db_date = latest.filing_date if latest else None

            # 拉 SEC EDGAR 最近的 13F filings（取最近 4 个季度足够判断是否有更新）
            sec_filings = await fetch_filings_sec(cik, quarters=4)
            if not sec_filings:
                logger.debug(f"No 13F filings on SEC for {name} (CIK {cik})")
                continue

            # SEC 返回的是字符串日期
            sec_dates = [f.get("filing_date") for f in sec_filings if f.get("filing_date")]
            if not sec_dates:
                continue
            latest_sec_date_str = max(sec_dates)
            try:
                latest_sec_date = date.fromisoformat(latest_sec_date_str)
            except ValueError:
                logger.warning(f"Invalid filing_date from SEC for {cik}: {latest_sec_date_str}")
                continue

            if latest_db_date is None or latest_sec_date > latest_db_date:
                logger.info(
                    f"New filing detected for {name} (CIK {cik}): "
                    f"DB={latest_db_date}, SEC={latest_sec_date}"
                )
                if cik not in updated_ciks:
                    updated_ciks.append(cik)
            else:
                logger.debug(f"{name}: up to date (latest={latest_db_date})")

        except Exception as e:
            logger.error(f"Failed to check filings for {name} (CIK {cik}): {e}")
            continue

    return updated_ciks


def daily_check():
    """每日检查任务"""
    logger.info("Running daily 13F check...")
    updated_ciks = asyncio.run(check_new_filings())
    if updated_ciks:
        logger.info(f"Found updates for {len(updated_ciks)} funds: {updated_ciks}")
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
