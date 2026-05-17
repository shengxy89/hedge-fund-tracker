"""View 3: 个股穿透 — 持有人 + 历史 + 拥挤度 + 情绪."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.charts import render_stacked_bar
from dashboard.components.disclaimer import sold_threshold_disclaimer
from dashboard.components.kpi_cards import kpi_stock_cards
from dashboard.data_access import (
    get_crowding_df,
    get_stock_history,
    get_stock_holders,
    get_stock_info,
    get_stock_jaccard_overlaps,
    get_stock_sentiment,
    search_stocks,
)
from dashboard.utils.formatters import get_action_badge


def render_stock_drill_view(quarter: str) -> None:
    """渲染个股穿透视图."""
    st.header("Stock Drill-down")

    # 搜索框
    search_input = st.text_input(
        "Search by Ticker / Name / CUSIP (min 2 chars)",
        value="AAPL",
        key="sd_search",
    ).strip()

    if not search_input or len(search_input) < 2:
        st.info("Enter at least 2 characters to search.")
        return

    # 模糊搜索
    results = search_stocks(search_input, limit=10)
    if results.empty:
        st.warning(f"No results found for '{search_input}'.")
        return

    # 如果有多个结果，让用户选择
    if len(results) > 1:
        options = [
            f"{r['ticker'] or '🌐'} | {r['stock_name']} | {r['cusip']}"
            for _, r in results.iterrows()
        ]
        choice = st.selectbox("Multiple matches found — select one:", options, key="sd_choice")
        idx = options.index(choice)
        selected = results.iloc[idx]
    else:
        selected = results.iloc[0]

    ticker = selected["ticker"]
    cusip = selected["cusip"]
    stock_name = selected["stock_name"]

    # 如果无 ticker，用 cusip 查 holdings
    query_key = ticker if ticker else cusip

    # KPI
    holders = get_stock_holders(query_key, quarter) if ticker else pd.DataFrame()
    if holders.empty and cusip:
        # fallback: 用 cusip 直接查
        holders = _get_holders_by_cusip(cusip, quarter)

    stock_info = get_stock_info(ticker) if ticker else {"name": stock_name}

    _render_stock_header(stock_info, ticker, stock_name, holders, quarter)

    if holders.empty:
        st.warning(f"No holding data found for {query_key} in {quarter}.")
        return

    # 主体 3 列
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        _render_holders_list(holders)
    with col2:
        _render_history_chart(ticker or cusip)
    with col3:
        _render_crowding_trend(ticker, quarter)

    # 底部：情绪指标
    st.markdown("---")
    _render_sentiment(cusip, quarter)

    # Jaccard
    if ticker:
        _render_jaccard(ticker, quarter)

    sold_threshold_disclaimer()


def _get_holders_by_cusip(cusip: str, quarter: str) -> pd.DataFrame:
    """用 CUSIP 查询持有人（无 ticker 的国际股）."""
    from utils import quarter_to_dates
    _, end_date = quarter_to_dates(quarter)
    report_date = end_date.isoformat()

    from sqlalchemy import text

    from db.engine import engine

    query = """
    SELECT
        f.name as fund_name,
        f.manager,
        h.shares,
        h.value,
        h.weight_pct,
        COALESCE(d.action, 'HOLD') as action,
        h.report_date as quarter_date
    FROM holdings h
    JOIN funds f ON h.fund_id = f.fund_id
    LEFT JOIN holding_deltas d ON h.fund_id = d.fund_id
        AND h.cusip = d.cusip AND d.quarter = :quarter
    WHERE h.cusip = :cusip AND h.report_date = :report_date
    ORDER BY h.value DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(
            text(query), conn, params={"cusip": cusip, "quarter": quarter, "report_date": report_date}
        )


def _render_stock_header(
    stock_info: dict,
    ticker: str | None,
    stock_name: str,
    holders: pd.DataFrame,
    quarter: str,
) -> None:
    """渲染个股头部 KPI."""
    st.subheader("Stock Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ticker", ticker or "🌐 NAME-only")
    col2.metric("Name", stock_info.get("name", stock_name) or stock_name)
    col3.metric("Sector", stock_info.get("sector", "N/A") or "N/A")
    col4.metric("Industry", stock_info.get("industry", "N/A") or "N/A")

    if holders.empty:
        return

    holder_count = len(holders)
    total_value = int(holders["value"].sum())
    total_shares = int(holders["shares"].sum())

    # 拥挤度排名
    crowding = get_crowding_df(quarter)
    crowding_rank = None
    if not crowding.empty and ticker:
        row = crowding[crowding["ticker"] == ticker]
        if not row.empty:
            crowding_rank = row.index[0] + 1

    kpi_stock_cards(holder_count, total_value, total_shares, crowding_rank)


def _render_holders_list(holders: pd.DataFrame) -> None:
    """渲染持有人列表."""
    st.subheader("Holding Funds")
    holders["Action"] = holders["action"].apply(get_action_badge)
    display_cols = ["fund_name", "shares", "value", "weight_pct", "Action"]
    rename_cols = ["Fund", "Shares", "Value($K)", "Weight%", "Action"]
    if "filing_date" in holders.columns:
        display_cols.append("filing_date")
        rename_cols.append("Filing Date")

    display = holders[display_cols].copy()
    display.columns = rename_cols
    st.dataframe(
        display.sort_values("Value($K)", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def _render_history_chart(ticker_or_cusip: str) -> None:
    """渲染历史持仓堆叠图."""
    st.subheader("Historical Ownership")
    hist = get_stock_history(ticker_or_cusip)
    if hist.empty:
        st.info("No historical data available.")
        return
    render_stacked_bar(hist, "report_date", "shares", "fund_name", "Ownership by Fund")


def _render_crowding_trend(ticker: str | None, quarter: str) -> None:
    """渲染拥挤度趋势."""
    st.subheader("Crowding Analysis")
    if not ticker:
        st.info("Crowding data requires ticker.")
        return

    crowding = get_crowding_df(quarter)
    if crowding.empty:
        st.info("No crowding data.")
        return

    row = crowding[crowding["ticker"] == ticker]
    if row.empty:
        st.info("Not in crowded stocks list.")
        return

    c = row.iloc[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Holder Count", int(c["holder_count"]))
    col2.metric("Crowding Score", f"{c['crowding_score']:.1%}")
    col3.metric("Avg Weight", f"{c['avg_weight']:.2f}%")


def _render_sentiment(cusip: str, quarter: str) -> None:
    """渲染情绪指标."""
    st.subheader("Sentiment Indicator")
    sent = get_stock_sentiment(cusip, quarter)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("NEW", sent["new_count"])
    c2.metric("SOLD", sent["sold_count"])
    c3.metric("ADD", sent["add_count"])
    c4.metric("REDUCE", sent["reduce_count"])

    net = sent["net_inflow"]
    if net > 0:
        st.success(f"🟢 Net Inflow: +{net} funds (bullish consensus building)")
    elif net < 0:
        st.error(f"🔴 Net Outflow: {net} funds (bearish consensus building)")
    else:
        st.info("⚪ Neutral: No net change in holder count")


def _render_jaccard(ticker: str, quarter: str) -> None:
    """渲染 Jaccard 趋同度."""
    st.subheader("Fund Convergence (Jaccard)")
    jaccard_df = get_stock_jaccard_overlaps(ticker, quarter)
    if jaccard_df.empty:
        st.info("No Jaccard data available.")
        return

    st.dataframe(
        jaccard_df[["fund_a_name", "fund_b_name", "jaccard_score", "overlap_count"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "jaccard_score": st.column_config.NumberColumn("Jaccard", format="%.3f"),
        },
    )
