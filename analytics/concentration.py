"""
单基金集中度分析模块
计算每个基金在每个季度的持仓集中度指标
"""

import pandas as pd
import polars as pl
from loguru import logger
from sqlalchemy import text

from db.engine import engine
from utils import date_to_quarter, quarter_to_dates


def _get_all_quarters_from_holdings() -> list[str]:
    """从 holdings 表中获取所有有数据的季度，升序排列"""
    query = "SELECT DISTINCT report_date FROM holdings ORDER BY report_date ASC"
    with engine.connect() as conn:
        result = conn.execute(text(query))
        raw_dates = [row[0] for row in result.fetchall()]

    from datetime import datetime
    dates = []
    for d in raw_dates:
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        dates.append(d)
    return list(dict.fromkeys(date_to_quarter(d) for d in dates))


def compute_fund_concentration(quarter: str) -> pd.DataFrame:
    """
    计算每个基金在指定季度的持仓集中度指标

    :param quarter: 目标季度，如 "2024Q3"
    :return: DataFrame，包含 fund_id, quarter, top_1_weight, top_5_weight,
             top_10_weight, hhi, holding_count, total_value
    """
    start_date, end_date = quarter_to_dates(quarter)

    # 查询该季度所有基金持仓
    query = """
        SELECT
            h.fund_id,
            h.report_date,
            h.value,
            h.weight_pct
        FROM holdings h
        JOIN funds f ON h.fund_id = f.fund_id
        WHERE h.report_date >= :start_date AND h.report_date <= :end_date
          AND (h.put_call IS NULL OR h.put_call = '' OR h.put_call = 'NONE')
        ORDER BY h.fund_id, h.value DESC
    """
    with engine.connect() as conn:
        df = pl.read_database(
            query, conn,
            execute_options={"parameters": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }}
        )

    if df.is_empty():
        return pd.DataFrame()

    # 按 fund_id 聚合计算集中度指标
    records = []
    for fund_id in df["fund_id"].unique().to_list():
        fund_df = df.filter(pl.col("fund_id") == fund_id)
        weights = fund_df["weight_pct"].to_list()
        values = fund_df["value"].to_list()

        if not weights:
            continue

        # 排序权重（已按 value DESC 排序，weight_pct 也应该是降序）
        sorted_weights = sorted(weights, reverse=True)

        top_1_weight = sorted_weights[0] if len(sorted_weights) >= 1 else 0
        top_5_weight = sum(sorted_weights[:5]) if len(sorted_weights) >= 1 else 0
        top_10_weight = sum(sorted_weights[:10]) if len(sorted_weights) >= 1 else 0

        # HHI = sum((weight_pct / 100) ^ 2)
        hhi = sum((w / 100) ** 2 for w in weights)

        holding_count = len(weights)
        total_value = sum(values)

        records.append({
            "fund_id": fund_id,
            "quarter": quarter,
            "top_1_weight": round(top_1_weight, 4),
            "top_5_weight": round(top_5_weight, 4),
            "top_10_weight": round(top_10_weight, 4),
            "hhi": round(hhi, 6),
            "holding_count": holding_count,
            "total_value": int(total_value),
        })

    return pd.DataFrame(records)


def run_concentration(quarter: str | None = None) -> int:
    """
    计算集中度并写入 fund_concentrations 表
    :param quarter: 指定季度，None 则计算所有有数据的季度
    :return: 写入的记录数
    """
    from db.engine import get_session
    from db.models import FundConcentration

    if quarter:
        quarters = [quarter]
    else:
        quarters = _get_all_quarters_from_holdings()

    total_count = 0
    for q in quarters:
        df = compute_fund_concentration(quarter=q)
        if df.empty:
            continue

        with get_session() as session:
            # 先清空该季度的旧数据
            session.execute(
                text("DELETE FROM fund_concentrations WHERE quarter = :q"),
                {"q": q},
            )
            session.commit()

            for _, row in df.iterrows():
                session.add(FundConcentration(
                    fund_id=int(row["fund_id"]),
                    quarter=str(row["quarter"]),
                    top_1_weight=float(row["top_1_weight"]),
                    top_5_weight=float(row["top_5_weight"]),
                    top_10_weight=float(row["top_10_weight"]),
                    hhi=float(row["hhi"]),
                    holding_count=int(row["holding_count"]),
                    total_value=int(row["total_value"]),
                ))
            session.commit()

        total_count += len(df)

    if total_count:
        logger.info(f"[OK] Concentration complete. {total_count} records computed.")
    else:
        logger.info("No concentration data to compute.")
    return total_count
