"""View 0: Overview 首页 — 宏观看板."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.charts import render_area_chart, render_horizontal_bar
from dashboard.components.disclaimer import filing_delay_badge
from dashboard.components.kpi_cards import kpi_overview_cards
from dashboard.data_access import (
    get_fund_activity_ranking,
    get_overview_kpi,
    get_sector_rotation,
    get_top_movers,
)


def render_overview_view(quarter: str) -> None:
    """渲染 Overview 首页视图."""
    st.header("Market Overview")

    kpi = get_overview_kpi(quarter)

    # 数据延迟徽章
    filing_delay_badge(kpi.get("report_date"), None)

    # KPI 卡
    kpi_overview_cards(kpi)

    st.markdown("---")

    # 中部两列：Top 买入 / 卖出
    col1, col2 = st.columns(2)
    with col1:
        _render_top_movers(quarter, "buy", "Top 10 Net Buy")
    with col2:
        _render_top_movers(quarter, "sell", "Top 10 Net Sell")

    st.markdown("---")

    # 底部两列：板块轮动 + 基金活跃度
    col1, col2 = st.columns(2)
    with col1:
        _render_sector_rotation()
    with col2:
        _render_fund_activity(quarter)


def _render_top_movers(quarter: str, direction: str, title: str) -> None:
    """渲染 Top movers 横向柱状图."""
    df = get_top_movers(quarter, direction, n=10)
    if df.empty:
        st.info(f"No {direction} data for this quarter.")
        return

    df = df.copy()
    df["display_label"] = df.apply(
        lambda r: r["ticker"] if pd.notna(r["ticker"]) else f"🌐 {str(r['stock_name'])[:12]}",
        axis=1,
    )
    df["abs_value"] = df["value_change"].abs()

    color_map = "#2E7D32" if direction == "buy" else "#C62828"

    render_horizontal_bar(
        df,
        x="abs_value",
        y="display_label",
        title=title,
        color_map={"": color_map},
        height=400,
    )

    with st.expander("View raw data"):
        display = df[["display_label", "stock_name", "sector", "action", "value_change"]].copy()
        display.columns = ["Ticker", "Name", "Sector", "Action", "Value Change ($K)"]
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_sector_rotation() -> None:
    """渲染板块轮动堆叠面积图."""
    df = get_sector_rotation(n_quarters=4)
    if df.empty:
        st.info("No sector rotation data.")
        return

    st.subheader("Sector Rotation (All Funds Avg)")
    render_area_chart(
        df,
        x="quarter",
        y="avg_weight_pct",
        color="sector",
        title="Sector Weight % Over Last 4 Quarters",
    )

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_fund_activity(quarter: str) -> None:
    """渲染基金活跃度排行."""
    df = get_fund_activity_ranking(quarter, n=10)
    if df.empty:
        st.info("No activity data.")
        return

    st.subheader("Most Active Funds")
    render_horizontal_bar(
        df,
        x="total_changes",
        y="fund_name",
        title="Total Position Changes (NEW + SOLD + ADD + REDUCE)",
        height=400,
    )

    with st.expander("View breakdown"):
        display = df[
            ["fund_name", "manager", "total_changes", "new_count", "sold_count", "add_count", "reduce_count"]
        ].copy()
        display.columns = [
            "Fund", "Manager", "Total", "NEW", "SOLD", "ADD", "REDUCE",
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)
