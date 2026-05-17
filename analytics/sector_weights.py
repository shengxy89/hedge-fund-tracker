"""
GICS 行业板块权重计算
"""
from datetime import datetime
from typing import Optional

import polars as pl
from loguru import logger
from sqlalchemy import text

from db.engine import engine
from db.models import SectorWeight
from utils import date_to_quarter


def compute_sector_weights_for_fund(fund_id: int, report_date) -> pl.DataFrame:
    """计算单个基金某季度的板块权重"""
    query = """
    SELECT 
        COALESCE(s.sector, 'Unknown') as sector,
        COUNT(*) as holding_count,
        SUM(h.value) as total_value
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    WHERE h.fund_id = :fund_id AND h.report_date = :report_date
    GROUP BY COALESCE(s.sector, 'Unknown')
    """
    date_str = report_date.isoformat() if hasattr(report_date, 'isoformat') else str(report_date)
    with engine.connect() as conn:
        df = pl.read_database(query, conn, execute_options={"parameters": {"fund_id": fund_id, "report_date": date_str}})

    if df.is_empty():
        return df

    # 计算该基金总市值
    total_query = """
    SELECT SUM(value) as total FROM holdings 
    WHERE fund_id = :fund_id AND report_date = :report_date
    """
    with engine.connect() as conn:
        result = conn.execute(text(total_query), {"fund_id": fund_id, "report_date": date_str})
        total = result.scalar() or 1

    # Ensure report_date is a date object for date_to_quarter
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    quarter = date_to_quarter(report_date)
    df = df.with_columns([
        pl.lit(fund_id).alias("fund_id"),
        pl.lit(quarter).alias("quarter"),
        (pl.col("total_value") / total * 100).alias("weight_pct"),
        pl.col("total_value").cast(pl.Float64),
    ])

    return df.select(["fund_id", "quarter", "sector", "weight_pct", "holding_count", "total_value"])


def run_sector_weights(quarter: Optional[str] = None):
    """运行板块权重计算"""
    from db.models import Fund
    from db.engine import get_session

    # 获取所有有数据的 (fund_id, report_date)
    query = """
    SELECT DISTINCT fund_id, report_date 
    FROM holdings 
    ORDER BY fund_id, report_date ASC
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    if quarter:
        parsed_rows = []
        for fid, rd in rows:
            if isinstance(rd, str):
                rd = datetime.strptime(rd, "%Y-%m-%d").date()
            if date_to_quarter(rd) == quarter:
                parsed_rows.append((fid, rd))
        rows = parsed_rows

    logger.info(f"Computing sector weights for {len(rows)} fund-quarter combinations...")

    all_weights = []
    for fund_id, report_date in rows:
        df = compute_sector_weights_for_fund(fund_id, report_date)
        if not df.is_empty():
            all_weights.append(df)

    if not all_weights:
        logger.info("No sector weights to compute.")
        return 0

    combined = pl.concat(all_weights)

    # 清空旧数据并写入
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sector_weights"))
        conn.commit()

    import pandas as pd
    pd_df = combined.to_pandas()
    pd_df.to_sql("sector_weights", engine, if_exists="append", index=False)

    logger.info(f"[OK] Sector weights complete. {len(pd_df)} records computed.")
    return len(pd_df)
