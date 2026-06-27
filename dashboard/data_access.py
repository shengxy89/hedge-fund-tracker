"""
Dashboard 数据访问层
提供统一的数据库查询接口
"""
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

from db.engine import engine
from utils import date_to_quarter, get_prev_quarter, quarter_to_dates

# =============================================================================
# 常量
# =============================================================================

_PC_FILTER: str = "(put_call IS NULL OR put_call = '' OR put_call = 'NONE')"
"""普通股过滤条件：排除 PUT/CALL 期权持仓."""


def get_available_quarters() -> list[str]:
    """获取所有有数据的季度，降序排列"""
    query = "SELECT DISTINCT report_date FROM holdings ORDER BY report_date DESC"
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    if df.empty:
        return []
    quarters = sorted(
        set(
            df["report_date"].apply(
                lambda x: date_to_quarter(
                    x if hasattr(x, "month") else date.fromisoformat(str(x))
                )
            )
        ),
        reverse=True,
    )
    return quarters


@st.cache_data(ttl=3600, show_spinner=False)
def get_funds_df() -> pd.DataFrame:
    """获取基金列表"""
    query = "SELECT fund_id, cik, name, manager, strategy FROM funds WHERE is_active = 1 ORDER BY name"
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def get_summary_metrics(quarter: str) -> dict:
    """获取顶部指标卡数据（单连接多查询，避免反复建连）"""
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    with engine.connect() as conn:
        # 追踪基金数（当季有持仓）
        total_funds = conn.execute(
            text("SELECT COUNT(DISTINCT fund_id) FROM holdings WHERE report_date = :rd"),
            {"rd": report_date},
        ).scalar() or 0

        # 当前季度总持仓股票数（去重）
        total_stocks = conn.execute(
            text(
                "SELECT COUNT(DISTINCT ticker) FROM holdings "
                "WHERE report_date = :rd AND ticker IS NOT NULL"
            ),
            {"rd": report_date},
        ).scalar() or 0

        # 最活跃调仓基金（一次 JOIN 取基金名）
        result = conn.execute(
            text("""
                SELECT d.fund_id, f.name, COUNT(*) as cnt
                FROM holding_deltas d
                JOIN funds f ON d.fund_id = f.fund_id
                WHERE d.quarter = :q AND d.action IN ('NEW', 'SOLD')
                GROUP BY d.fund_id, f.name
                ORDER BY cnt DESC
                LIMIT 1
            """),
            {"q": quarter},
        ).fetchone()
        active_fund_name = result[1] if result else ""
        active_count = result[2] if result else 0

        # 最拥挤股票 Top 1
        result = conn.execute(
            text("""
                SELECT ticker, COUNT(DISTINCT fund_id) as cnt
                FROM holdings
                WHERE report_date = :rd AND ticker IS NOT NULL
                  AND (put_call IS NULL OR put_call = '')
                GROUP BY ticker
                ORDER BY cnt DESC
                LIMIT 1
            """),
            {"rd": report_date},
        ).fetchone()
        crowded_ticker = result[0] if result else ""
        crowded_count = result[1] if result else 0

        # 当前季度最晚 filing_date（数据延迟参考）
        latest_filing_date = conn.execute(
            text("SELECT MAX(filing_date) FROM filings WHERE report_date = :rd"),
            {"rd": report_date},
        ).scalar() or ""

    return {
        "total_funds": int(total_funds),
        "total_stocks": int(total_stocks),
        "active_fund": active_fund_name,
        "active_count": int(active_count),
        "crowded_ticker": crowded_ticker,
        "crowded_count": int(crowded_count),
        "report_date": report_date,
        "latest_filing_date": str(latest_filing_date) if latest_filing_date else "",
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_heatmap_data(quarter: str, min_holders: int = 3, selected_sectors: list | None = None) -> pd.DataFrame:
    """
    获取热力图数据
    返回 DataFrame: fund_name x ticker -> action_code
    """
    start_date, end_date = quarter_to_dates(quarter)

    # 参数化查询避免 SQL 拼接；sector 过滤在 DataFrame 后处理
    query = """
    SELECT
        f.name as fund_name,
        h.ticker,
        h.name as stock_name,
        COALESCE(s.sector, 'Unknown') as sector,
        COALESCE(d.action, 'HOLD') as action,
        h.shares,
        h.value,
        h.weight_pct
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    LEFT JOIN securities s ON h.cusip = s.cusip
    LEFT JOIN holding_deltas d ON h.fund_id = d.fund_id
        AND h.cusip = d.cusip
        AND COALESCE(h.put_call, 'NONE') = COALESCE(d.put_call, 'NONE')
        AND d.quarter = :quarter
    WHERE h.report_date >= :start_date AND h.report_date <= :end_date
    AND h.ticker IN (
        SELECT ticker FROM holdings
        WHERE report_date >= :start_date AND report_date <= :end_date
        AND ticker IS NOT NULL
        GROUP BY ticker
        HAVING COUNT(DISTINCT fund_id) >= :min_holders
    )
    ORDER BY f.name, h.ticker
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query),
            conn,
            params={
                "quarter": quarter,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "min_holders": min_holders,
            },
        )

    # 在 pandas 中过滤 sector，避免 SQL 拼接用户输入
    if selected_sectors:
        df = df[df["sector"].isin(selected_sectors + ["Unknown"])]

    # action -> numeric code
    action_map = {"NEW": 2, "ADD": 1, "HOLD": 0, "REDUCE": -1, "SOLD": -2}
    df["action_code"] = df["action"].map(action_map).fillna(0)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def get_fund_holdings(fund_id: int, quarter: str) -> pd.DataFrame:
    """获取某基金某季度的持仓明细"""
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT
        h.ticker,
        h.name as stock_name,
        COALESCE(s.sector, 'Unknown') as sector,
        h.shares,
        h.value,
        h.weight_pct,
        COALESCE(d.action, 'HOLD') as action,
        d.shares_change_pct
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    LEFT JOIN holding_deltas d ON h.fund_id = d.fund_id
        AND h.cusip = d.cusip
        AND COALESCE(h.put_call, 'NONE') = COALESCE(d.put_call, 'NONE')
        AND d.quarter = :quarter
    WHERE h.fund_id = :fund_id AND h.report_date = :report_date
    ORDER BY h.value DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"fund_id": fund_id, "quarter": quarter, "report_date": report_date})


@st.cache_data(ttl=3600, show_spinner=False)
def get_fund_deltas(fund_id: int, quarter: str) -> pd.DataFrame:
    """获取某基金某季度的调仓变化"""
    query = """
    SELECT * FROM holding_deltas
    WHERE fund_id = :fund_id AND quarter = :quarter
    ORDER BY ABS(value_change) DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"fund_id": fund_id, "quarter": quarter})


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_holders(ticker: str, quarter: str) -> pd.DataFrame:
    """获取持有某股票的所有基金"""
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT
        f.name as fund_name,
        f.manager,
        h.shares,
        h.value,
        h.weight_pct,
        COALESCE(d.action, 'HOLD') as action,
        h.report_date as quarter_date,
        fil.filing_date
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    LEFT JOIN (
        SELECT fund_id, report_date, MAX(filing_date) as filing_date
        FROM filings
        WHERE report_date = :report_date
        GROUP BY fund_id, report_date
    ) fil ON h.fund_id = fil.fund_id AND h.report_date = fil.report_date
    LEFT JOIN holding_deltas d ON h.fund_id = d.fund_id
        AND h.cusip = d.cusip
        AND COALESCE(h.put_call, 'NONE') = COALESCE(d.put_call, 'NONE')
        AND d.quarter = :quarter
    WHERE h.ticker = :ticker AND h.report_date = :report_date
    ORDER BY h.value DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"ticker": ticker, "quarter": quarter, "report_date": report_date})


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_history(ticker: str) -> pd.DataFrame:
    """获取某股票的历史持仓（各基金 shares 堆叠）"""
    query = """
    SELECT
        h.report_date,
        f.name as fund_name,
        h.shares
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    WHERE h.ticker = :ticker
    ORDER BY h.report_date, f.name
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"ticker": ticker})


@st.cache_data(ttl=3600, show_spinner=False)
def get_sector_weights_fund(fund_id: int, quarter: str) -> pd.DataFrame:
    """获取某基金某季度的板块权重"""
    query = """
    SELECT sector, weight_pct, holding_count, total_value
    FROM sector_weights
    WHERE fund_id = :fund_id AND quarter = :quarter
    ORDER BY weight_pct DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"fund_id": fund_id, "quarter": quarter})


@st.cache_data(ttl=3600, show_spinner=False)
def get_crowding_df(quarter: str) -> pd.DataFrame:
    """获取拥挤度排行"""
    from analytics.crowding import get_crowding_report
    df = get_crowding_report(quarter)
    return df.to_pandas()


@st.cache_data(ttl=3600, show_spinner=False)
def get_sector_weight_heatmap(quarter: str) -> pd.DataFrame:
    """
    获取板块权重热力图数据
    返回 DataFrame: fund_name x sector -> weight_pct
    """
    query = """
    SELECT
        f.name as fund_name,
        sw.sector,
        sw.weight_pct
    FROM sector_weights sw
    JOIN funds f ON sw.fund_id = f.fund_id
    WHERE sw.quarter = :quarter
    ORDER BY f.name, sw.weight_pct DESC
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"quarter": quarter})
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_jaccard_overlaps(ticker: str, quarter: str) -> pd.DataFrame:
    """
    获取持有某股票的所有基金之间的 Jaccard 趋同度
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT
        fa.name as fund_a_name,
        fb.name as fund_b_name,
        fo.jaccard_score,
        fo.overlap_count,
        fo.overlap_tickers
    FROM fund_overlaps fo
    JOIN funds fa ON fo.fund_a_id = fa.fund_id
    JOIN funds fb ON fo.fund_b_id = fb.fund_id
    WHERE fo.quarter = :quarter
    AND fo.fund_a_id IN (
        SELECT DISTINCT fund_id FROM holdings
        WHERE ticker = :ticker AND report_date = :report_date
    )
    AND fo.fund_b_id IN (
        SELECT DISTINCT fund_id FROM holdings
        WHERE ticker = :ticker AND report_date = :report_date
    )
    ORDER BY fo.jaccard_score DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"ticker": ticker, "quarter": quarter, "report_date": report_date})


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_info(ticker: str) -> dict:
    """获取股票基本信息"""
    query = "SELECT ticker, name, sector, industry FROM securities WHERE ticker = :ticker LIMIT 1"
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"ticker": ticker})
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "ticker": row["ticker"],
        "name": row["name"],
        "sector": row["sector"],
        "industry": row["industry"],
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_filing_info(fund_id: int, quarter: str) -> dict:
    """获取某基金某季度的 filing 信息（report_date vs filing_date）"""
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT report_date, filing_date, form_type, is_amendment, total_value, holding_count
    FROM filings
    WHERE fund_id = :fund_id AND report_date = :report_date
    ORDER BY filing_date DESC
    LIMIT 1
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"fund_id": fund_id, "report_date": report_date})

    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "report_date": str(row["report_date"]),
        "filing_date": str(row["filing_date"]),
        "form_type": row["form_type"],
        "is_amendment": bool(row["is_amendment"]),
        "total_value": int(row["total_value"] or 0),
        "holding_count": int(row["holding_count"] or 0),
    }


# =============================================================================
# Phase 0 新增查询函数（8个）
# =============================================================================


@st.cache_data(ttl=3600, show_spinner=False)
def get_overview_kpi(quarter: str) -> dict[str, Any]:
    """获取 Overview 首页的 4 个 KPI 指标.

    Args:
        quarter: 季度字符串，如 "2025Q1".

    Returns:
        dict，包含以下键：
            - total_funds (int): 本季有持仓的基金数.
            - total_value (int): 本季总持仓市值（千美元）.
            - prev_total_value (int): 上季总持仓市值（千美元）.
            - value_change_pct (float | None): 环比变化百分比.
            - new_stock_count (int): 本季 NEW 建仓的 distinct 股票数.
            - crowded_ticker (str): 最拥挤股票的 ticker.
            - crowded_count (int): 持有最拥挤股票的基金数.
            - report_date (str): 本季 report_date.
            - prev_quarter (str): 上一季度字符串.
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()
    prev_q = get_prev_quarter(quarter)
    _, prev_end = quarter_to_dates(prev_q)
    prev_report_date = prev_end.isoformat()

    with engine.connect() as conn:
        # 追踪基金数
        total_funds = conn.execute(
            text(f"SELECT COUNT(DISTINCT fund_id) FROM holdings WHERE report_date = :rd AND {_PC_FILTER}"),
            {"rd": report_date},
        ).scalar() or 0

        # 本季总持仓市值
        total_value = conn.execute(
            text(f"SELECT COALESCE(SUM(value), 0) FROM holdings WHERE report_date = :rd AND {_PC_FILTER}"),
            {"rd": report_date},
        ).scalar() or 0

        # 上季总持仓市值
        prev_value = conn.execute(
            text(f"SELECT COALESCE(SUM(value), 0) FROM holdings WHERE report_date = :rd AND {_PC_FILTER}"),
            {"rd": prev_report_date},
        ).scalar() or 0

        # NEW 个股数
        new_count = conn.execute(
            text(f"""
                SELECT COUNT(DISTINCT cusip) FROM holding_deltas
                WHERE quarter = :q AND action = 'NEW' AND {_PC_FILTER}
            """),
            {"q": quarter},
        ).scalar() or 0

        # 最拥挤股票
        result = conn.execute(
            text(f"""
                SELECT ticker, COUNT(DISTINCT fund_id) as cnt
                FROM holdings
                WHERE report_date = :rd AND ticker IS NOT NULL AND {_PC_FILTER}
                GROUP BY ticker ORDER BY cnt DESC LIMIT 1
            """),
            {"rd": report_date},
        )
        row = result.fetchone()
        crowded_ticker = row[0] if row else ""
        crowded_count = row[1] if row else 0

    value_change_pct = None
    if prev_value and prev_value > 0:
        value_change_pct = (total_value - prev_value) / prev_value

    return {
        "total_funds": int(total_funds),
        "total_value": int(total_value),
        "prev_total_value": int(prev_value),
        "value_change_pct": value_change_pct,
        "new_stock_count": int(new_count),
        "crowded_ticker": crowded_ticker or "",
        "crowded_count": int(crowded_count),
        "report_date": report_date,
        "prev_quarter": prev_q,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_top_movers(quarter: str, direction: str, n: int = 10) -> pd.DataFrame:
    """获取本季净买入或净卖出 Top N 股票.

    Args:
        quarter: 季度字符串，如 "2025Q1".
        direction: "buy" 或 "sell". buy 取 NEW/ADD，sell 取 SOLD/REDUCE.
        n: 返回条数，默认 10.

    Returns:
        DataFrame，列：
            ticker, stock_name, sector, action, shares_change, value_change,
            weight_prev, weight_curr
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    if direction == "buy":
        actions_sql = "('NEW', 'ADD')"
        order = "DESC"
    else:
        actions_sql = "('SOLD', 'REDUCE')"
        order = "ASC"

    query = f"""
    SELECT
        h.ticker,
        h.name as stock_name,
        COALESCE(s.sector, 'Unknown') as sector,
        d.action,
        d.shares_change,
        d.value_change,
        d.weight_prev,
        d.weight_curr
    FROM holding_deltas d
    JOIN holdings h
        ON d.fund_id = h.fund_id
        AND d.cusip = h.cusip
        AND h.report_date = :report_date
    LEFT JOIN securities s ON d.cusip = s.cusip
    WHERE d.quarter = :quarter
      AND d.action IN {actions_sql}
      AND (d.put_call IS NULL OR d.put_call = '' OR d.put_call = 'NONE')
    ORDER BY d.value_change {order}
    LIMIT :limit
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text(query),
            conn,
            params={
                "quarter": quarter,
                "report_date": report_date,
                "limit": n,
            },
        )
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def get_sector_rotation(n_quarters: int = 4) -> pd.DataFrame:
    """获取最近 N 个季度的板块轮动数据（全体基金平均）.

    Args:
        n_quarters: 最近几个季度，默认 4.

    Returns:
        DataFrame，列：
            quarter, sector, avg_weight_pct, total_value, holding_count
    """
    query = """
    WITH latest_quarters AS (
        SELECT DISTINCT quarter
        FROM sector_weights
        ORDER BY quarter DESC
        LIMIT :n
    )
    SELECT
        sw.quarter,
        sw.sector,
        ROUND(AVG(sw.weight_pct), 2) as avg_weight_pct,
        SUM(sw.total_value) as total_value,
        SUM(sw.holding_count) as holding_count
    FROM sector_weights sw
    WHERE sw.quarter IN (SELECT quarter FROM latest_quarters)
    GROUP BY sw.quarter, sw.sector
    ORDER BY sw.quarter DESC, avg_weight_pct DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params={"n": n_quarters})


@st.cache_data(ttl=3600, show_spinner=False)
def get_fund_activity_ranking(quarter: str, n: int = 10) -> pd.DataFrame:
    """获取本季度调仓活跃度最高的基金排行.

    Args:
        quarter: 季度字符串.
        n: 返回条数，默认 10.

    Returns:
        DataFrame，列：
            fund_id, fund_name, manager, total_changes,
            new_count, sold_count, add_count, reduce_count
    """
    query = """
    SELECT
        f.fund_id,
        f.name as fund_name,
        f.manager,
        COUNT(*) as total_changes,
        SUM(CASE WHEN d.action = 'NEW' THEN 1 ELSE 0 END) as new_count,
        SUM(CASE WHEN d.action = 'SOLD' THEN 1 ELSE 0 END) as sold_count,
        SUM(CASE WHEN d.action = 'ADD' THEN 1 ELSE 0 END) as add_count,
        SUM(CASE WHEN d.action = 'REDUCE' THEN 1 ELSE 0 END) as reduce_count
    FROM holding_deltas d
    JOIN funds f ON d.fund_id = f.fund_id
    WHERE d.quarter = :quarter
      AND (d.put_call IS NULL OR d.put_call = '' OR d.put_call = 'NONE')
    GROUP BY f.fund_id, f.name, f.manager
    ORDER BY total_changes DESC
    LIMIT :limit
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params={"quarter": quarter, "limit": n})


@st.cache_data(ttl=3600, show_spinner=False)
def get_options_summary(quarter: str, option_type: str) -> pd.DataFrame:
    """获取期权持仓汇总（CALL 或 PUT）.

    Args:
        quarter: 季度字符串.
        option_type: "CALL" 或 "PUT".

    Returns:
        DataFrame，列：
            ticker, stock_name, cusip, sector, holder_count,
            total_shares, total_value, avg_weight_pct
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    query = """
    SELECT
        h.ticker,
        h.name as stock_name,
        h.cusip,
        COALESCE(s.sector, 'Unknown') as sector,
        COUNT(DISTINCT h.fund_id) as holder_count,
        SUM(h.shares) as total_shares,
        SUM(h.value) as total_value,
        ROUND(AVG(h.weight_pct), 2) as avg_weight_pct
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    WHERE h.report_date = :report_date
      AND UPPER(h.put_call) = :option_type
    GROUP BY h.ticker, h.name, h.cusip, s.sector
    ORDER BY total_value DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(
            text(query),
            conn,
            params={"report_date": report_date, "option_type": option_type.upper()},
        )


@st.cache_data(ttl=3600, show_spinner=False)
def get_fund_pair_overlap_detail(
    fund_a: int, fund_b: int, quarter: str
) -> dict[str, Any]:
    """获取两基金的详细对比数据（共同持仓、Jaccard、反向操作等）.

    Args:
        fund_a: 基金 A 的 fund_id.
        fund_b: 基金 B 的 fund_id.
        quarter: 季度字符串.

    Returns:
        dict，包含以下键：
            - common_holdings (pd.DataFrame): 共同持仓明细.
            - jaccard_history (pd.DataFrame): 最近 8 季度 Jaccard 趋势.
            - common_add (pd.DataFrame): 共同加仓列表.
            - common_reduce (pd.DataFrame): 共同减仓列表.
            - reverse_actions (pd.DataFrame): 一方 NEW 另一方 SOLD.
    """
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    with engine.connect() as conn:
        # 共同持仓
        common_q = """
        SELECT
            COALESCE(h1.ticker, h1.name) as display_label,
            h1.name as stock_name,
            h1.shares as shares_a,
            h1.value as value_a,
            h1.weight_pct as weight_a,
            h2.shares as shares_b,
            h2.value as value_b,
            h2.weight_pct as weight_b
        FROM holdings h1
        JOIN holdings h2
            ON h1.cusip = h2.cusip
            AND h1.report_date = h2.report_date
        WHERE h1.fund_id = :fund_a
          AND h2.fund_id = :fund_b
          AND h1.report_date = :report_date
          AND (h1.put_call IS NULL OR h1.put_call = '' OR h1.put_call = 'NONE')
          AND (h2.put_call IS NULL OR h2.put_call = '' OR h2.put_call = 'NONE')
        ORDER BY (h1.value + h2.value) DESC
        """
        common_holdings = pd.read_sql(
            text(common_q),
            conn,
            params={"fund_a": fund_a, "fund_b": fund_b, "report_date": report_date},
        )

        # Jaccard 历史趋势
        jaccard_q = """
        SELECT quarter, jaccard_score, overlap_count
        FROM fund_overlaps
        WHERE (
            (fund_a_id = :fund_a AND fund_b_id = :fund_b)
            OR (fund_a_id = :fund_b AND fund_b_id = :fund_a)
        )
        ORDER BY quarter DESC
        LIMIT 8
        """
        jaccard_history = pd.read_sql(
            text(jaccard_q),
            conn,
            params={"fund_a": fund_a, "fund_b": fund_b},
        )

        # 共同 ADD
        add_q = """
        SELECT
            COALESCE(d1.ticker, '') as ticker,
            d1.shares_change as shares_change_a,
            d1.value_change as value_change_a,
            d2.shares_change as shares_change_b,
            d2.value_change as value_change_b
        FROM holding_deltas d1
        JOIN holding_deltas d2
            ON d1.cusip = d2.cusip
            AND d1.quarter = d2.quarter
        WHERE d1.fund_id = :fund_a
          AND d2.fund_id = :fund_b
          AND d1.quarter = :quarter
          AND d1.action = 'ADD'
          AND d2.action = 'ADD'
          AND (d1.put_call IS NULL OR d1.put_call = '' OR d1.put_call = 'NONE')
        ORDER BY (d1.value_change + d2.value_change) DESC
        """
        common_add = pd.read_sql(
            text(add_q),
            conn,
            params={"fund_a": fund_a, "fund_b": fund_b, "quarter": quarter},
        )

        # 共同 REDUCE
        reduce_q = """
        SELECT
            COALESCE(d1.ticker, '') as ticker,
            d1.shares_change as shares_change_a,
            d1.value_change as value_change_a,
            d2.shares_change as shares_change_b,
            d2.value_change as value_change_b
        FROM holding_deltas d1
        JOIN holding_deltas d2
            ON d1.cusip = d2.cusip
            AND d1.quarter = d2.quarter
        WHERE d1.fund_id = :fund_a
          AND d2.fund_id = :fund_b
          AND d1.quarter = :quarter
          AND d1.action = 'REDUCE'
          AND d2.action = 'REDUCE'
          AND (d1.put_call IS NULL OR d1.put_call = '' OR d1.put_call = 'NONE')
        ORDER BY (d1.value_change + d2.value_change) ASC
        """
        common_reduce = pd.read_sql(
            text(reduce_q),
            conn,
            params={"fund_a": fund_a, "fund_b": fund_b, "quarter": quarter},
        )

        # 反向操作
        reverse_q = """
        SELECT
            COALESCE(d1.ticker, '') as ticker,
            d1.action as action_a,
            d2.action as action_b,
            d1.value_change as value_change_a,
            d2.value_change as value_change_b
        FROM holding_deltas d1
        JOIN holding_deltas d2
            ON d1.cusip = d2.cusip
            AND d1.quarter = d2.quarter
        WHERE d1.fund_id = :fund_a
          AND d2.fund_id = :fund_b
          AND d1.quarter = :quarter
          AND (
              (d1.action = 'NEW' AND d2.action = 'SOLD')
              OR (d1.action = 'SOLD' AND d2.action = 'NEW')
          )
          AND (d1.put_call IS NULL OR d1.put_call = '' OR d1.put_call = 'NONE')
        ORDER BY ABS(d1.value_change) + ABS(d2.value_change) DESC
        """
        reverse_actions = pd.read_sql(
            text(reverse_q),
            conn,
            params={"fund_a": fund_a, "fund_b": fund_b, "quarter": quarter},
        )

    return {
        "common_holdings": common_holdings,
        "jaccard_history": jaccard_history,
        "common_add": common_add,
        "common_reduce": common_reduce,
        "reverse_actions": reverse_actions,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def search_stocks(keyword: str, limit: int = 20) -> pd.DataFrame:
    """按 ticker / name / cusip 模糊搜索股票.

    Args:
        keyword: 搜索关键词，至少 2 个字符.
        limit: 返回条数上限，默认 20.

    Returns:
        DataFrame，列：
            cusip, ticker, stock_name, sector
    """
    if not keyword or len(keyword.strip()) < 2:
        return pd.DataFrame(columns=["cusip", "ticker", "stock_name", "sector"])

    kw = f"%{keyword.strip().upper()}%"
    query = """
    SELECT DISTINCT
        h.cusip,
        h.ticker,
        h.name as stock_name,
        COALESCE(s.sector, 'Unknown') as sector
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    WHERE (
        (h.ticker IS NOT NULL AND UPPER(h.ticker) LIKE :kw)
        OR UPPER(h.name) LIKE :kw
        OR UPPER(h.cusip) LIKE :kw
    )
    LIMIT :limit
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params={"kw": kw, "limit": limit})


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_sentiment(cusip: str, quarter: str) -> dict[str, Any]:
    """获取某股票在指定季度的情绪指标.

    Args:
        cusip: CUSIP 编号.
        quarter: 季度字符串.

    Returns:
        dict，包含：
            - new_count (int): NEW 的基金数.
            - sold_count (int): SOLD 的基金数.
            - add_count (int): ADD 的基金数.
            - reduce_count (int): REDUCE 的基金数.
            - net_inflow (int): 净流入基金数 = new_count - sold_count.
            - holder_count (int): 当前持有该股票的基金数.
    """
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT
                    SUM(CASE WHEN action = 'NEW' THEN 1 ELSE 0 END) as new_count,
                    SUM(CASE WHEN action = 'SOLD' THEN 1 ELSE 0 END) as sold_count,
                    SUM(CASE WHEN action = 'ADD' THEN 1 ELSE 0 END) as add_count,
                    SUM(CASE WHEN action = 'REDUCE' THEN 1 ELSE 0 END) as reduce_count,
                    COUNT(DISTINCT fund_id) as holder_count
                FROM holding_deltas
                WHERE cusip = :cusip
                  AND quarter = :quarter
                  AND (put_call IS NULL OR put_call = '' OR put_call = 'NONE')
            """),
            {"cusip": cusip, "quarter": quarter},
        )
        row = result.fetchone()

    if not row:
        return {
            "new_count": 0, "sold_count": 0, "add_count": 0,
            "reduce_count": 0, "net_inflow": 0, "holder_count": 0,
        }

    new_count = int(row[0] or 0)
    sold_count = int(row[1] or 0)
    add_count = int(row[2] or 0)
    reduce_count = int(row[3] or 0)
    holder_count = int(row[4] or 0)

    return {
        "new_count": new_count,
        "sold_count": sold_count,
        "add_count": add_count,
        "reduce_count": reduce_count,
        "net_inflow": new_count - sold_count,
        "holder_count": holder_count,
    }


# =============================================================================
# 共识信号查询
# =============================================================================

@st.cache_data(ttl=3600)
def get_consensus_signals(
    quarter: str,
    action: str | None = None,
    min_funds: int = 2,
    min_score: float = 0.0,
    top_n: int = 50,
) -> pd.DataFrame:
    """获取多基金调仓共识信号"""
    sql = """
        SELECT
            n.cusip,
            COALESCE(s.ticker, n.cusip) as ticker,
            s.name as issuer,
            s.sector,
            n.consensus_action as action,
            n.fund_count,
            n.avg_weight_change_pct,
            n.total_weight_change_pct,
            n.signal_score,
            n.fund_size_tier,
            n.action_norm_score,
            n.conviction_score,
            n.holder_count,
            n.crowding_score
        FROM holding_delta_norms n
        LEFT JOIN securities s ON n.cusip = s.cusip
        WHERE n.quarter = :quarter
          AND n.fund_count >= :min_funds
          AND n.signal_score >= :min_score
    """
    params: dict[str, Any] = {"quarter": quarter, "min_funds": min_funds, "min_score": min_score}
    if action:
        sql += " AND n.consensus_action = :action"
        params["action"] = action

    sql += " ORDER BY n.signal_score DESC LIMIT :top_n"
    params["top_n"] = top_n

    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


@st.cache_data(ttl=3600)
def get_consensus_kpi(quarter: str) -> dict[str, int]:
    """获取共识信号 KPI 统计"""
    sql = """
        SELECT
            consensus_action,
            COUNT(*) as cnt,
            SUM(fund_count) as total_fund_participation
        FROM holding_delta_norms
        WHERE quarter = :quarter
        GROUP BY consensus_action
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params={"quarter": quarter})

    kpi = {"total": 0, "new": 0, "sold": 0, "add": 0, "reduce": 0, "avg_fund_count": 0.0}
    total_participation = 0
    for _, row in df.iterrows():
        action = row["consensus_action"].lower()
        cnt = int(row["cnt"])
        kpi[action] = cnt
        kpi["total"] += cnt
        total_participation += int(row["total_fund_participation"])

    if kpi["total"] > 0:
        kpi["avg_fund_count"] = round(total_participation / kpi["total"], 1)

    return kpi


@st.cache_data(ttl=3600)
def get_consensus_fund_detail(
    quarter: str, cusip: str, put_call: str | None = None
) -> pd.DataFrame:
    """获取某共识标的具体参与的基金明细"""
    if put_call is None:
        pc_filter = "AND (d.put_call IS NULL OR d.put_call = '' OR d.put_call = 'NONE')"
    else:
        pc_filter = "AND d.put_call = :put_call"
    sql = f"""
        SELECT
            f.name as fund_name,
            f.manager,
            d.action,
            d.weight_change_pct,
            d.weight_prev,
            d.weight_curr,
            d.value_change
        FROM holding_deltas d
        JOIN funds f ON d.fund_id = f.fund_id
        WHERE d.quarter = :quarter
          AND d.cusip = :cusip
          {pc_filter}
        ORDER BY ABS(d.weight_change_pct) DESC
    """
    params: dict[str, Any] = {"quarter": quarter, "cusip": cusip}
    if put_call:
        params["put_call"] = put_call

    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)
