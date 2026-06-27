"""多基金调仓共识信号引擎

核心思路：weight_change_pct（权重变化百分比）和 value_change（绝对金额变化）
作为跨基金可比指标，聚合多基金对同一标的的共识调仓信号。

signal_score 公式：
    signal_score =
        fund_count * abs(avg_weight_change_pct)
        + log10(1 + abs(total_value_change)) * 2
        + holder_count * 0.5

解释：
- fund_count * abs(avg_weight_change_pct)：比例反映 conviction（信念强度）
- log10(1 + abs(total_value_change)) * 2：绝对金额反映实际资本流向
- holder_count * 0.5：反映拥挤度/共识范围
"""
from __future__ import annotations

import polars as pl
from sqlalchemy import text

from db.engine import get_session
from utils import quarter_to_dates

# ──────────────────────────────
#  辅助函数
# ──────────────────────────────


def _resolve_consensus_quarter(quarter: str | None) -> str | None:
    """解析 consensus 目标季度。若传入 None，返回 holding_deltas 中最新的季度。"""
    if quarter:
        return quarter
    with get_session(read_only=True) as session:
        result = session.execute(
            text("SELECT DISTINCT quarter FROM holding_deltas ORDER BY quarter")
        )
        quarters = [r[0] for r in result.fetchall()]
        return quarters[-1] if quarters else None


def _get_fund_size_tier(session, fund_ids: list[int] | None) -> dict[int, str]:
    """根据基金最新持仓总市值划分规模档次"""
    fund_query = "SELECT fund_id, name FROM funds"
    if fund_ids:
        # 显式转 int 后再拼接，避免字符串注入
        safe_ids = ",".join(str(int(fid)) for fid in fund_ids)
        fund_query += f" WHERE fund_id IN ({safe_ids})"
    result = session.execute(text(fund_query))
    funds = result.fetchall()

    # 用 holdings 计算最新总市值（取各基金最新 report_date）
    value_query = """
        SELECT h.fund_id, SUM(h.value) as total_value
        FROM holdings h
        JOIN (
            SELECT fund_id, MAX(report_date) as max_date
            FROM holdings
            GROUP BY fund_id
        ) latest ON h.fund_id = latest.fund_id AND h.report_date = latest.max_date
        GROUP BY h.fund_id
    """
    result = session.execute(text(value_query))
    total_by_fund = {row[0]: row[1] for row in result.fetchall()}

    tiers: dict[int, str] = {}
    for fid, name in funds:
        total = total_by_fund.get(fid, 0)
        if total >= 5_000_000:       # >= $5B
            tier = "mega"
        elif total >= 1_000_000:     # >= $1B
            tier = "large"
        elif total >= 200_000:       # >= $200M
            tier = "medium"
        else:
            tier = "small"
        tiers[fid] = tier
    return tiers


# ──────────────────────────────
#  核心共识计算
# ──────────────────────────────


def compute_consensus(
    quarter: str | None = None,
    min_funds: int = 3,
    add_reduce_threshold: float = 1.0,
    fund_ids: list[int] | None = None,
) -> pl.DataFrame:
    """计算多基金调仓共识信号

    :param quarter: 目标季度，如 "2024Q4"；None 表示最新有数据的季度
    :param min_funds: 最少参与基金数
    :param add_reduce_threshold: ADD/REDUCE 共识的 weight_change_pct 阈值（百分点）
    :param fund_ids: 限定基金范围
    :return: 共识信号 DataFrame
    """
    # 确定季度（提前固定，避免下游丢失）
    actual_quarter = _resolve_consensus_quarter(quarter)
    if actual_quarter is None:
        return pl.DataFrame()

    # 直接从 holding_deltas 表读取，包含金额和权重字段
    delta_sql = """
        SELECT d.fund_id, d.cusip, d.put_call, d.quarter,
               d.action, d.weight_change_pct,
               d.value_change, d.value_curr, d.value_prev, d.value_change_pct,
               d.weight_curr, d.weight_prev,
               s.name as issuer,
               s.sector, s.industry
        FROM holding_deltas d
        JOIN securities s ON d.cusip = s.cusip
        WHERE d.quarter = :quarter
    """

    with get_session(read_only=True) as session:
        result = session.execute(text(delta_sql), {"quarter": actual_quarter})
        rows = result.mappings().all()

    if not rows:
        return pl.DataFrame()

    delta_df = pl.DataFrame([dict(r) for r in rows])
    if delta_df.is_empty():
        return pl.DataFrame()

    # 若限定 fund_ids，在 Python 层过滤（避免 SQL 拼接风险）
    if fund_ids:
        safe_fund_ids = [int(fid) for fid in fund_ids]
        delta_df = delta_df.filter(pl.col("fund_id").is_in(safe_fund_ids))
        if delta_df.is_empty():
            return pl.DataFrame()

    # ── 获取当前季度各标的的 holder_count（拥挤度）──
    # 使用日期范围查询，避免只依赖季度最后一天
    start_date, end_date = quarter_to_dates(actual_quarter)
    crowding_sql = """
        SELECT cusip, COUNT(DISTINCT fund_id) as holder_count
        FROM holdings
        WHERE report_date >= :start_date AND report_date <= :end_date
          AND (put_call IS NULL OR put_call = '' OR put_call = 'NONE')
        GROUP BY cusip
    """
    with get_session(read_only=True) as session:
        result = session.execute(
            text(crowding_sql),
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )
        crowding_rows = result.mappings().all()

    crowding_df = pl.DataFrame([dict(r) for r in crowding_rows])
    if not crowding_df.is_empty():
        delta_df = delta_df.join(crowding_df, on="cusip", how="left")
    else:
        delta_df = delta_df.with_columns(pl.lit(0).alias("holder_count"))

    # 填充 put_call null
    delta_df = delta_df.with_columns(
        pl.col("put_call").fill_null("NONE")
    )

    # 辅助聚合表达式（避免重复）
    base_aggs = [
        pl.len().alias("fund_count"),
        pl.mean("weight_change_pct").alias("avg_weight_change_pct"),
        pl.sum("weight_change_pct").alias("total_weight_change_pct"),
        pl.sum("value_change").alias("total_value_change"),
        pl.mean("value_change").alias("avg_value_change"),
        pl.col("value_change").abs().sum().alias("total_abs_value_change"),
        pl.mean("value_change_pct").alias("avg_value_change_pct"),
        pl.mean("weight_curr").alias("avg_weight_curr"),
        pl.sum("weight_curr").alias("total_weight_curr"),
        pl.col("fund_id").alias("fund_ids"),
        pl.max("holder_count").alias("holder_count"),
    ]

    # 1) 共识 NEW: ≥N 家基金同时新建仓
    consensus_new = (
        delta_df.filter(pl.col("action") == "NEW")
        .group_by(["cusip", "put_call", "issuer", "sector", "industry"])
        .agg(base_aggs)
        .filter(pl.col("fund_count") >= min_funds)
        .with_columns([
            pl.lit("NEW").alias("consensus_action"),
            pl.lit(actual_quarter).alias("quarter"),
        ])
    )

    # 2) 共识 SOLD: ≥N 家基金同时清仓
    consensus_sold = (
        delta_df.filter(pl.col("action") == "SOLD")
        .group_by(["cusip", "put_call", "issuer", "sector", "industry"])
        .agg(base_aggs)
        .filter(pl.col("fund_count") >= min_funds)
        .with_columns([
            pl.lit("SOLD").alias("consensus_action"),
            pl.lit(actual_quarter).alias("quarter"),
        ])
    )

    # 3) 共识 ADD: ≥N 家基金同时增持，且平均 weight_change_pct > 阈值
    consensus_add = (
        delta_df.filter(pl.col("action") == "ADD")
        .group_by(["cusip", "put_call", "issuer", "sector", "industry"])
        .agg(base_aggs)
        .filter(
            (pl.col("fund_count") >= min_funds)
            & (pl.col("avg_weight_change_pct") >= add_reduce_threshold)
        )
        .with_columns([
            pl.lit("ADD").alias("consensus_action"),
            pl.lit(actual_quarter).alias("quarter"),
        ])
    )

    # 4) 共识 REDUCE: ≥N 家基金同时减持，且平均 weight_change_pct < -阈值
    consensus_reduce = (
        delta_df.filter(pl.col("action") == "REDUCE")
        .group_by(["cusip", "put_call", "issuer", "sector", "industry"])
        .agg(base_aggs)
        .filter(
            (pl.col("fund_count") >= min_funds)
            & (pl.col("avg_weight_change_pct") <= -add_reduce_threshold)
        )
        .with_columns([
            pl.lit("REDUCE").alias("consensus_action"),
            pl.lit(actual_quarter).alias("quarter"),
        ])
    )

    # 合并所有共识信号
    consensus = pl.concat(
        [consensus_new, consensus_sold, consensus_add, consensus_reduce],
        how="diagonal_relaxed",
    )

    if consensus.is_empty():
        return consensus

    # 计算信号强度 score
    # 比例反映 conviction，绝对金额反映实际资本流向，holder_count 反映拥挤度/共识范围
    consensus = consensus.with_columns(
        (
            pl.col("fund_count") * pl.col("avg_weight_change_pct").abs()
            + (1 + pl.col("total_value_change").abs()).log10() * 2
            + pl.col("holder_count").fill_null(0) * 0.5
        ).alias("signal_score")
    )

    # 获取总基金数计算 crowding_score
    with get_session(read_only=True) as session:
        result = session.execute(text("SELECT COUNT(*) FROM funds WHERE is_active = 1"))
        total_funds = result.scalar() or 1

    consensus = consensus.with_columns(
        (pl.col("holder_count").fill_null(0) / total_funds).alias("crowding_score")
    )

    # 排序：信号强度降序
    consensus = consensus.sort("signal_score", descending=True)

    return consensus


# ──────────────────────────────
#  标准化表写入
# ──────────────────────────────


def write_consensus_to_db(
    quarter: str | None = None,
    min_funds: int = 3,
    add_reduce_threshold: float = 1.0,
) -> int:
    """计算共识信号并写入 holding_delta_norms 表

    :return: 写入的记录数
    """
    from db.models import HoldingDeltaNorm

    # 提前解析季度，不依赖 consensus_df 中的字段
    actual_quarter = _resolve_consensus_quarter(quarter)
    if actual_quarter is None:
        return 0

    consensus_df = compute_consensus(
        quarter=actual_quarter,
        min_funds=min_funds,
        add_reduce_threshold=add_reduce_threshold,
    )

    if consensus_df.is_empty():
        return 0

    # 获取基金规模档次
    with get_session(read_only=True) as session:
        fund_tiers = _get_fund_size_tier(session, None)

    records: list[dict] = []
    for row in consensus_df.to_dicts():
        # 计算 fund_size_tier（按参与基金的规模加权或取多数）
        fids = row.get("fund_ids", [])
        if not fids:
            continue
        tiers = [fund_tiers.get(fid, "unknown") for fid in fids]
        # 取最常见的 tier
        from collections import Counter

        tier_counter = Counter(tiers)
        fund_size_tier = tier_counter.most_common(1)[0][0]

        # action_norm_score: 标准化动作强度
        # NEW/SOLD = 固定高值 + fund_count 加权；ADD/REDUCE = avg_weight_change_pct 加权
        action = row["consensus_action"]
        if action in ("NEW", "SOLD"):
            action_norm_score = 50.0 + row["fund_count"] * 5.0
        else:
            action_norm_score = abs(row["avg_weight_change_pct"]) * row["fund_count"] * 2.0

        # conviction_score: 综合置信度
        conviction_score = row["signal_score"] * (1 + row["fund_count"] * 0.1)

        records.append(
            {
                "quarter": actual_quarter,
                "cusip": row["cusip"],
                "put_call": None if row["put_call"] == "NONE" else row["put_call"],
                "consensus_action": action,
                "fund_count": row["fund_count"],
                "avg_weight_change_pct": round(row["avg_weight_change_pct"], 4),
                "total_weight_change_pct": round(row.get("total_weight_change_pct", 0) or 0, 4),
                "signal_score": round(row["signal_score"], 4),
                "fund_size_tier": fund_size_tier,
                "action_norm_score": round(action_norm_score, 4),
                "conviction_score": round(conviction_score, 4),
                "holder_count": int(row.get("holder_count", 0) or 0),
                "crowding_score": round(row.get("crowding_score", 0) or 0, 4),
                "total_value_change": int(row.get("total_value_change", 0) or 0),
                "avg_value_change": round(row.get("avg_value_change", 0) or 0, 4),
                "total_abs_value_change": int(row.get("total_abs_value_change", 0) or 0),
                "avg_value_change_pct": round(row.get("avg_value_change_pct", 0) or 0, 4),
                "avg_weight_curr": round(row.get("avg_weight_curr", 0) or 0, 4),
                "total_weight_curr": round(row.get("total_weight_curr", 0) or 0, 4),
            }
        )

    if not records:
        return 0

    with get_session() as session:
        # 先清空该季度的旧数据
        session.execute(
            text("DELETE FROM holding_delta_norms WHERE quarter = :q"), {"q": actual_quarter}
        )
        session.commit()

        for rec in records:
            session.add(HoldingDeltaNorm(**rec))
        session.commit()

    return len(records)
