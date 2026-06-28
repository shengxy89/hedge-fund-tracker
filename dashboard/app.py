#!/usr/bin/env python3
"""Streamlit 主应用入口 — 13F Alpha Tracker."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

import config.logging  # noqa: F401 — activate loguru handlers
from dashboard.components.disclaimer import filing_delay_badge
from dashboard.components.filters import render_sidebar
from dashboard.data_access import get_summary_metrics
from dashboard.theme import init_theme
from dashboard.views.compare_funds import render_compare_funds_view
from dashboard.views.consensus_view import render_consensus_view
from dashboard.views.crowding_leaderboard import render_crowding_view
from dashboard.views.fund_drill import render_fund_drill_view
from dashboard.views.fund_ranking import render_fund_ranking_view
from dashboard.views.heatmap import render_heatmap_view
from dashboard.views.options_view import render_options_view
from dashboard.views.overview import render_overview_view
from dashboard.views.stock_drill import render_stock_drill_view

st.set_page_config(
    page_title="13F Alpha Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化主题
init_theme()


def main() -> None:
    """主入口."""
    # 侧边栏
    selected_quarter, selected_fund_ids, selected_sectors, refresh = render_sidebar()

    if selected_quarter is None:
        st.title("13F Alpha Tracker")
        st.info("Welcome! Please initialize the database and run ETL to load data.")
        st.code("python scripts/run_full_pipeline.py --mock", language="bash")
        return

    # 顶部标题
    st.title(f"13F Alpha Tracker — {selected_quarter}")

    # 顶部指标卡（全局摘要）
    metrics = get_summary_metrics(selected_quarter)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tracking Funds", metrics["total_funds"])
    col2.metric("Unique Stocks", metrics["total_stocks"])
    col3.metric("Most Active Fund", metrics["active_fund"], f"{metrics['active_count']} changes")
    col4.metric("Most Crowded", metrics["crowded_ticker"], f"{metrics['crowded_count']} holders")

    # 数据延迟徽章
    filing_delay_badge(
        report_date=metrics.get("report_date"),
        filing_date=metrics.get("latest_filing_date"),
    )

    st.markdown("---")

    # 标签页
    tabs = st.tabs([
        "🏠 Overview",
        "📊 Heatmap",
        "🏦 Fund Drill-down",
        "📈 Stock Drill-down",
        "📋 Crowding",
        "🛡️ Options",
        "⚖️ Compare Funds",
        "🎯 Consensus",
        "🏆 Fund Ranking",
    ])

    with tabs[0]:
        render_overview_view(selected_quarter)

    with tabs[1]:
        render_heatmap_view(selected_quarter, selected_fund_ids, selected_sectors)

    with tabs[2]:
        render_fund_drill_view(selected_quarter, selected_fund_ids, selected_sectors)

    with tabs[3]:
        render_stock_drill_view(selected_quarter, selected_fund_ids, selected_sectors)

    with tabs[4]:
        render_crowding_view(selected_quarter)

    with tabs[5]:
        render_options_view(selected_quarter)

    with tabs[6]:
        render_compare_funds_view(selected_quarter, selected_fund_ids)

    with tabs[7]:
        render_consensus_view(selected_quarter)

    with tabs[8]:
        render_fund_ranking_view(selected_quarter)


if __name__ == "__main__":
    main()
