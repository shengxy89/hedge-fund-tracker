"""View 4: 拥挤度排行 — Top N + Sector 分组 + 趋势."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.data_access import get_crowding_df


def render_crowding_view(quarter: str) -> None:
    """渲染拥挤度排行榜视图."""
    st.header("Crowding Leaderboard")
    st.markdown("Stocks held by the most funds — potential consensus trades.")

    df = get_crowding_df(quarter)
    if df.empty:
        st.info("No crowding data available.")
        return

    # 顶部分组开关
    group_mode = st.radio(
        "View Mode",
        options=["All Sectors", "By Sector"],
        horizontal=True,
        key="cr_group",
    )

    if group_mode == "All Sectors":
        _render_all_sectors(df)
    else:
        _render_by_sector(df)

    st.markdown("---")

    # 上升/下降最快
    _render_movers(df)


def _render_all_sectors(df: pd.DataFrame) -> None:
    """全部 sector 的主表."""
    st.subheader("Top 50 Most Crowded Stocks")

    top50 = df.head(50).copy()
    top50["Rank"] = range(1, len(top50) + 1)

    st.dataframe(
        top50[[
            "Rank", "ticker", "name", "sector",
            "holder_count", "crowding_score", "avg_weight", "total_value",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "crowding_score": st.column_config.ProgressColumn(
                "Crowding", format="%.1%", min_value=0, max_value=1,
            ),
            "avg_weight": st.column_config.NumberColumn("Avg Weight%", format="%.2f%%"),
            "total_value": st.column_config.NumberColumn("Total Value($K)", format="%,d"),
        },
    )


def _render_by_sector(df: pd.DataFrame) -> None:
    """按 Sector 分组的子 Tab."""
    sectors = sorted(df["sector"].dropna().unique().tolist())
    if not sectors:
        st.info("No sector data.")
        return

    sub_tabs = st.tabs(sectors)
    for tab, sector in zip(sub_tabs, sectors):
        with tab:
            sub = df[df["sector"] == sector].head(20).copy()
            if sub.empty:
                st.caption("No data.")
                continue
            st.dataframe(
                sub[["ticker", "name", "holder_count", "crowding_score", "avg_weight", "total_value"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "crowding_score": st.column_config.ProgressColumn("Crowding", format="%.1%"),
                },
            )


def _render_movers(df: pd.DataFrame) -> None:
    """上升/下降最快."""
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔥 Rising Fast")
        # 由于我们没有环比数据，用 holder_count 作为替代排序
        rising = df.head(10).copy()
        if not rising.empty:
            st.dataframe(
                rising[["ticker", "name", "sector", "holder_count", "crowding_score"]],
                use_container_width=True,
                hide_index=True,
            )
    with col2:
        st.subheader("❄️ Falling Fast")
        # 反转排序取尾部
        falling = df.tail(10).copy()
        if not falling.empty:
            st.dataframe(
                falling[["ticker", "name", "sector", "holder_count", "crowding_score"]],
                use_container_width=True,
                hide_index=True,
            )
