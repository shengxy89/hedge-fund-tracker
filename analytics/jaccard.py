"""
基金间选股趋同度计算（Jaccard Similarity）
"""
from itertools import combinations
from typing import Optional

from datetime import datetime

import polars as pl
from loguru import logger
from sqlalchemy import text

from db.engine import engine
from db.models import FundOverlap
from utils import date_to_quarter


def get_fund_holdings_by_quarter(quarter: str) -> dict[int, set[str]]:
    """
    获取某季度每个基金的持仓 ticker 集合（仅普通股，排除期权）
    返回: {fund_id: set(ticker, ...)}
    """
    query = """
    SELECT h.fund_id, h.ticker
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    WHERE h.report_date = (
        SELECT MAX(report_date) FROM holdings 
        WHERE date_to_quarter(report_date) = :quarter
    )
    AND (h.put_call IS NULL OR h.put_call = '')
    AND h.ticker IS NOT NULL
    """
    # SQLite 没有 date_to_quarter，改用直接日期匹配
    from utils import quarter_to_dates
    start, end = quarter_to_dates(quarter)

    query = """
    SELECT h.fund_id, h.ticker
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    WHERE h.report_date = :report_date
    AND (h.put_call IS NULL OR h.put_call = '')
    AND h.ticker IS NOT NULL
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {"report_date": end.isoformat()})
        rows = result.fetchall()

    holdings = {}
    for fund_id, ticker in rows:
        holdings.setdefault(fund_id, set()).add(ticker)
    return holdings


def compute_jaccard_for_quarter(quarter: str) -> pl.DataFrame:
    """计算某季度所有基金对的 Jaccard 相似度"""
    holdings = get_fund_holdings_by_quarter(quarter)
    fund_ids = sorted(holdings.keys())

    if len(fund_ids) < 2:
        return pl.DataFrame()

    records = []
    for a, b in combinations(fund_ids, 2):
        set_a = holdings[a]
        set_b = holdings[b]
        intersection = set_a & set_b
        union = set_a | set_b
        jaccard = len(intersection) / len(union) if len(union) > 0 else 0
        records.append({
            "fund_a_id": a,
            "fund_b_id": b,
            "quarter": quarter,
            "jaccard_score": round(jaccard, 6),
            "overlap_count": len(intersection),
            "overlap_tickers": ",".join(sorted(intersection)),
        })

    return pl.DataFrame(records)


def run_jaccard(quarter: Optional[str] = None):
    """
    计算基金间趋同度
    :param quarter: 指定季度，None 则计算所有有数据的季度
    """
    if quarter:
        quarters = [quarter]
    else:
        # 获取所有有数据的 quarter
        query = "SELECT DISTINCT report_date FROM holdings ORDER BY report_date ASC"
        with engine.connect() as conn:
            result = conn.execute(text(query))
            raw_dates = [row[0] for row in result.fetchall()]
            dates = []
            for d in raw_dates:
                if isinstance(d, str):
                    d = datetime.strptime(d, "%Y-%m-%d").date()
                dates.append(d)
        quarters = list(dict.fromkeys(date_to_quarter(d) for d in dates))

    logger.info(f"Running Jaccard for quarters: {quarters}")

    all_overlaps = []
    for q in quarters:
        df = compute_jaccard_for_quarter(q)
        if not df.is_empty():
            all_overlaps.append(df)

    if not all_overlaps:
        logger.info("No overlaps computed.")
        return 0

    combined = pl.concat(all_overlaps)

    # 增量替换：仅删除本次计算涉及的 quarter
    quarters_touched = sorted({q for q in combined["quarter"].to_list() if q})
    with engine.connect() as conn:
        if quarters_touched:
            placeholders = ",".join(f":q{i}" for i in range(len(quarters_touched)))
            params = {f"q{i}": q for i, q in enumerate(quarters_touched)}
            conn.execute(text(f"DELETE FROM fund_overlaps WHERE quarter IN ({placeholders})"), params)
        conn.commit()

    import pandas as pd
    pd_df = combined.to_pandas()
    pd_df.to_sql("fund_overlaps", engine, if_exists="append", index=False)

    logger.info(f"[OK] Jaccard complete. {len(pd_df)} overlap records computed for quarters {quarters_touched}.")
    return len(pd_df)
