#!/usr/bin/env python3
"""
为数据库中已有的 holdings 补充 ticker 信息
同时修复错误 ticker（如 COM, CL A 等 titleOfClass 值）
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from db.engine import get_session
from db.models import Holding, Security
from etl.cusip_resolver import resolve_cusips_batch

# 常见的错误 ticker（来自 SEC XML 的 titleOfClass）
BAD_TICKERS = {"COM", "CL A", "CL B", "SHS", "NOTE", "COMM", "ORD", "ADS", "CALL", "ADR", "SPONSORED ADS"}


async def update_all_tickers():
    """为所有缺失或错误 ticker 的 CUSIP 补充信息"""
    with get_session() as session:
        # 1. 先修复 holdings 表中的错误 ticker
        bad_count = session.query(Holding).filter(Holding.ticker.in_(BAD_TICKERS)).count()
        if bad_count > 0:
            logger.info(f"Fixing {bad_count} holdings with bad tickers...")
            session.query(Holding).filter(Holding.ticker.in_(BAD_TICKERS)).update(
                {Holding.ticker: None}, synchronize_session=False
            )
            logger.info("Bad tickers cleared")

        # 2. 删除 securities 表中的错误记录
        session.query(Security).filter(Security.ticker.in_(BAD_TICKERS)).delete(synchronize_session=False)

        # 3. 找出所有需要解析的 unique CUSIP
        cusips = (
            session.query(Holding.cusip)
            .filter(Holding.ticker.is_(None))
            .group_by(Holding.cusip)
            .all()
        )
        missing = [c[0] for c in cusips if c[0]]

    logger.info(f"Found {len(missing)} CUSIPs without ticker info")
    if not missing:
        return

    # 4. 批量解析
    batch_size = 10
    total_updated = 0
    for i in range(0, len(missing), batch_size):
        batch = missing[i : i + batch_size]
        resolved = await resolve_cusips_batch(batch)
        resolved_tickers = {k: v.get("ticker") for k, v in resolved.items() if v.get("ticker")}

        # 5. 更新 holdings 表
        if resolved_tickers:
            with get_session() as session:
                for cusip, ticker in resolved_tickers.items():
                    count = (
                        session.query(Holding)
                        .filter(Holding.cusip == cusip, Holding.ticker.is_(None))
                        .update({Holding.ticker: ticker}, synchronize_session=False)
                    )
                    total_updated += count

        logger.info(
            f"Batch {i // batch_size + 1}/{(len(missing) + batch_size - 1) // batch_size}: "
            f"resolved {len(resolved_tickers)} tickers, updated {total_updated} holdings"
        )

    logger.info(f"Updated ticker info for {total_updated} holdings")


if __name__ == "__main__":
    asyncio.run(update_all_tickers())
