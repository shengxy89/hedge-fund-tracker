"""
市场拥挤度计算
"""
from typing import Optional

import polars as pl
from sqlalchemy import text

from db.engine import engine
from utils import date_to_quarter, quarter_to_dates


def get_crowding_report(quarter: str, min_holders: int = 2) -> pl.DataFrame:
    """
    获取某季度的拥挤度报告
    :param quarter: 季度格式如 "2024Q3"
    :param min_holders: 最少持有基金数阈值
    :return: Polars DataFrame
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT 
        h.ticker,
        MAX(h.name) as name,
        MAX(COALESCE(s.sector, 'Unknown')) as sector,
        COUNT(DISTINCT h.fund_id) as holder_count,
        AVG(h.weight_pct) as avg_weight,
        SUM(h.value) as total_value
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    WHERE h.report_date = :report_date
    AND (h.put_call IS NULL OR h.put_call = '')
    AND h.ticker IS NOT NULL
    GROUP BY h.ticker
    HAVING COUNT(DISTINCT h.fund_id) >= :min_holders
    ORDER BY holder_count DESC, total_value DESC
    """

    with engine.connect() as conn:
        df = pl.read_database(query, conn, execute_options={"parameters": {"report_date": report_date, "min_holders": min_holders}})

    if df.is_empty():
        return df

    # 获取追踪中基金总数（拥挤度分母应用所有追踪基金，而非当季有持仓的基金数）
    total_funds_query = "SELECT COUNT(*) FROM funds WHERE is_active = 1"
    with engine.connect() as conn:
        result = conn.execute(text(total_funds_query))
        total_funds = result.scalar() or 1

    if total_funds <= 0:
        total_funds = 1

    df = df.with_columns([
        (pl.col("holder_count") / total_funds).alias("crowding_score"),
        pl.lit(quarter).alias("quarter"),
    ])

    # 重排列顺序
    df = df.select([
        "ticker", "name", "sector", "holder_count",
        "crowding_score", "avg_weight", "total_value", "quarter"
    ])

    return df


def get_top_crowded(quarter: str, top_n: int = 20) -> pl.DataFrame:
    """获取最拥挤的 Top N 股票"""
    df = get_crowding_report(quarter)
    return df.head(top_n)
