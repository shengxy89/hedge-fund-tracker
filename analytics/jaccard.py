"""
基金间选股趋同度计算（Jaccard Similarity）
增加加权 Jaccard 和重合持仓市值占比指标
"""
from datetime import datetime
from itertools import combinations

import polars as pl
from loguru import logger
from sqlalchemy import text

from db.engine import engine
from utils import date_to_quarter, quarter_to_dates


def get_fund_holdings_by_quarter(quarter: str) -> dict[int, set[str]]:
    """
    获取某季度每个基金的持仓 ticker 集合（仅普通股，排除期权）
    返回: {fund_id: set(ticker, ...)}
    """
    start_date, end_date = quarter_to_dates(quarter)

    query = """
    SELECT h.fund_id, h.ticker
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    WHERE h.report_date >= :start_date AND h.report_date <= :end_date
    AND (h.put_call IS NULL OR h.put_call = '' OR h.put_call = 'NONE')
    AND h.ticker IS NOT NULL
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        })
        rows = result.fetchall()

    holdings = {}
    for fund_id, ticker in rows:
        holdings.setdefault(fund_id, set()).add(ticker)
    return holdings


def get_fund_holdings_with_weights(quarter: str) -> dict[int, dict[str, dict]]:
    """
    获取某季度每个基金的持仓 ticker 及其权重、市值
    返回: {
        fund_id: {
            ticker: {"weight_pct": float, "value": float}
        }
    }
    """
    start_date, end_date = quarter_to_dates(quarter)

    query = """
    SELECT h.fund_id, h.ticker, h.weight_pct, h.value
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    WHERE h.report_date >= :start_date AND h.report_date <= :end_date
    AND (h.put_call IS NULL OR h.put_call = '' OR h.put_call = 'NONE')
    AND h.ticker IS NOT NULL
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        })
        rows = result.fetchall()

    holdings: dict[int, dict[str, dict]] = {}
    for fund_id, ticker, weight_pct, value in rows:
        if fund_id not in holdings:
            holdings[fund_id] = {}
        holdings[fund_id][ticker] = {
            "weight_pct": float(weight_pct or 0),
            "value": float(value or 0),
        }
    return holdings


def compute_jaccard_for_quarter(quarter: str) -> pl.DataFrame:
    """计算某季度所有基金对的 Jaccard 相似度（普通 + 加权）"""
    holdings_sets = get_fund_holdings_by_quarter(quarter)
    holdings_weights = get_fund_holdings_with_weights(quarter)
    fund_ids = sorted(holdings_sets.keys())

    if len(fund_ids) < 2:
        return pl.DataFrame()

    records = []
    for a, b in combinations(fund_ids, 2):
        set_a = holdings_sets[a]
        set_b = holdings_sets[b]
        intersection = set_a & set_b
        union = set_a | set_b

        # 普通 Jaccard
        jaccard = len(intersection) / len(union) if len(union) > 0 else 0

        # 加权 Jaccard
        weights_a = holdings_weights.get(a, {})
        weights_b = holdings_weights.get(b, {})

        min_sum = 0.0
        max_sum = 0.0
        for ticker in union:
            wa = weights_a.get(ticker, {}).get("weight_pct", 0)
            wb = weights_b.get(ticker, {}).get("weight_pct", 0)
            min_sum += min(wa, wb)
            max_sum += max(wa, wb)

        weighted_jaccard = min_sum / max_sum if max_sum > 0 else 0

        # 重合持仓市值占比
        total_value_a = sum(v.get("value", 0) for v in weights_a.values())
        total_value_b = sum(v.get("value", 0) for v in weights_b.values())

        overlap_value_a = sum(
            weights_a.get(ticker, {}).get("value", 0) for ticker in intersection
        )
        overlap_value_b = sum(
            weights_b.get(ticker, {}).get("value", 0) for ticker in intersection
        )

        overlap_value_pct_a = (overlap_value_a / total_value_a * 100) if total_value_a > 0 else 0
        overlap_value_pct_b = (overlap_value_b / total_value_b * 100) if total_value_b > 0 else 0

        records.append({
            "fund_a_id": a,
            "fund_b_id": b,
            "quarter": quarter,
            "jaccard_score": round(jaccard, 6),
            "weighted_jaccard_score": round(weighted_jaccard, 6),
            "overlap_count": len(intersection),
            "overlap_tickers": ",".join(sorted(intersection)),
            "overlap_value_pct_a": round(overlap_value_pct_a, 4),
            "overlap_value_pct_b": round(overlap_value_pct_b, 4),
        })

    return pl.DataFrame(records)


def run_jaccard(quarter: str | None = None):
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

    # 仅删除本次涉及的季度，避免全表清空
    quarters_touched = sorted({q for q in combined["quarter"].to_list() if q})
    with engine.connect() as conn:
        if quarters_touched:
            placeholders = ",".join(f":q{i}" for i in range(len(quarters_touched)))
            params = {f"q{i}": q for i, q in enumerate(quarters_touched)}
            conn.execute(text(f"DELETE FROM fund_overlaps WHERE quarter IN ({placeholders})"), params)
        conn.commit()

    pd_df = combined.to_pandas()
    pd_df.to_sql("fund_overlaps", engine, if_exists="append", index=False)

    logger.info(f"[OK] Jaccard complete. {len(pd_df)} overlap records computed.")
    return len(pd_df)
