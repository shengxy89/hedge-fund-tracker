"""View: 基金综合排行榜 — 多维排名 + 趋同散点."""

from __future__ import annotations

import streamlit as st

from dashboard.components.charts import render_horizontal_bar, render_scatter
from dashboard.data_access import (
    get_concentration_ranking,
    get_fund_activity_ranking,
    get_fund_avg_jaccard,
    get_fund_pairs,
)
from dashboard.utils.exporters import render_csv_download_button


def render_fund_ranking_view(quarter: str) -> None:
    """渲染基金综合排行榜视图."""
    st.header("Fund Ranking")
    st.caption("多维度横向对比：调仓活跃度 · 持仓集中度 · 趋同度。")

    tabs = st.tabs(["调仓活跃度", "持仓集中度", "趋同度", "趋同散点"])

    with tabs[0]:
        df = get_fund_activity_ranking(quarter, n=20)
        if df.empty:
            st.info("No activity data.")
        else:
            render_horizontal_bar(
                df, x="total_changes", y="fund_name", title="调仓次数排行"
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
            render_csv_download_button(df, f"fund_activity_{quarter}.csv")

    with tabs[1]:
        df = get_concentration_ranking(quarter, top_n=20)
        if df.empty:
            st.info("暂无集中度数据（请先运行 concentration 分析）。")
        else:
            render_horizontal_bar(
                df, x="hhi", y="fund_name", title="HHI 集中度排行（越高越集中）"
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
            render_csv_download_button(df, f"fund_concentration_{quarter}.csv")

    with tabs[2]:
        df = get_fund_avg_jaccard(quarter)
        if df.empty:
            st.info("暂无趋同度数据。")
        else:
            render_horizontal_bar(
                df, x="avg_weighted_jaccard", y="fund_name",
                title="平均加权 Jaccard 排行（越高越趋同）",
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
            render_csv_download_button(df, f"fund_jaccard_{quarter}.csv")

    with tabs[3]:
        pairs = get_fund_pairs(quarter)
        if pairs.empty:
            st.info("暂无基金对数据。")
        else:
            render_scatter(
                pairs,
                x="weighted_jaccard_score",
                y="overlap_value_pct_a",
                hover_name="fund_a",
                title="加权 Jaccard vs 重合市值占比（每点一对基金）",
            )
            st.caption(
                "右上=高趋同+高重合市值（策略高度相似）；"
                "左下=低趋同（差异化）。"
            )
            st.dataframe(pairs, use_container_width=True, hide_index=True)
