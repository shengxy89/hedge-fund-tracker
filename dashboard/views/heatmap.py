"""View 1: 热力图 — 调仓矩阵 + 板块矩阵（双模式切换）."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.charts import render_heatmap
from dashboard.data_access import get_funds_df, get_heatmap_data, get_sector_weight_heatmap


def render_heatmap_view(
    quarter: str,
    selected_fund_ids: list[int],
    selected_sectors: list[str],
) -> None:
    """渲染热力图视图."""
    st.header("Position Change Heatmap")

    mode = st.radio(
        "Select Heatmap Mode",
        options=["Position Changes", "Sector Weights"],
        horizontal=True,
        key="hm_mode",
        help="Position Changes: Green=NEW/ADD, Red=REDUCE/SOLD | "
        "Sector Weights: Blues color scale showing GICS sector allocation",
    )

    if mode == "Position Changes":
        _render_position_heatmap(quarter, selected_fund_ids, selected_sectors)
    else:
        _render_sector_heatmap(quarter, selected_fund_ids)


def _render_position_heatmap(
    quarter: str,
    selected_fund_ids: list[int],
    selected_sectors: list[str],
) -> None:
    """模式 A: 调仓热力图."""
    st.markdown("Green = NEW/ADD, Red = REDUCE/SOLD, Grey = HOLD")

    # 三层过滤控件
    c1, c2, c3 = st.columns(3)
    with c1:
        min_holders = st.selectbox("Min Holders", [1, 2, 3, 5, 10], index=2, key="hm_min_holders")
    with c2:
        top_n = st.selectbox("Top N Stocks", [10, 30, 50, 100], index=1, key="hm_top_n")
    with c3:
        sort_by = st.selectbox(
            "Sort by",
            ["Holder Count", "Total Value", "Net Buy"],
            index=0,
            key="hm_sort",
        )

    df = get_heatmap_data(
        quarter,
        min_holders=min_holders,
        selected_sectors=selected_sectors or None,
    )
    if df.empty:
        st.info("No data available for this quarter.")
        return

    # 基金筛选
    if selected_fund_ids:
        funds_df = get_funds_df()
        fund_names = funds_df[funds_df["fund_id"].isin(selected_fund_ids)]["name"].tolist()
        df = df[df["fund_name"].isin(fund_names)]

    if df.empty:
        st.info("No data after filtering.")
        return

    # 按排序规则计算股票排名
    if sort_by == "Holder Count":
        stock_rank = df.groupby("ticker")["fund_name"].nunique().sort_values(ascending=False)
    elif sort_by == "Total Value":
        stock_rank = df.groupby("ticker")["value"].sum().sort_values(ascending=False)
    else:  # Net Buy
        net_buy = df[df["action"].isin(["NEW", "ADD"])].groupby("ticker").size()
        stock_rank = net_buy.sort_values(ascending=False)

    top_stocks = stock_rank.head(top_n).index.tolist()
    df = df[df["ticker"].isin(top_stocks)]

    if df.empty:
        st.info("No data after Top N filter.")
        return

    # 基金排序
    activity = (
        df[df["action"].isin(["NEW", "SOLD"])]
        .groupby("fund_name")
        .size()
        .reindex(df["fund_name"].unique(), fill_value=0)
    )
    fund_order = activity.sort_values(ascending=False).index.tolist()

    # 构建矩阵
    pivot = df.pivot_table(
        index="fund_name",
        columns="ticker",
        values="action_code",
        aggfunc="first",
    )
    pivot = pivot.reindex(fund_order)

    # hover 信息
    hover_details = df.pivot_table(
        index="fund_name",
        columns="ticker",
        values="action",
        aggfunc="first",
    )
    hover_details = hover_details.reindex(index=pivot.index, columns=pivot.columns)

    hover_texts = hover_details.copy().astype(object)
    for fund in hover_texts.index:
        for ticker in hover_texts.columns:
            action = (
                hover_details.at[fund, ticker]
                if fund in hover_details.index and ticker in hover_details.columns
                else None
            )
            if pd.isna(action):
                hover_texts.at[fund, ticker] = "Not held"
            else:
                row = df[(df["fund_name"] == fund) & (df["ticker"] == ticker)]
                if not row.empty:
                    shares = row.iloc[0].get("shares", 0)
                    value = row.iloc[0].get("value", 0)
                    w = row.iloc[0].get("weight_pct", 0)
                    hover_texts.at[fund, ticker] = (
                        f"Action: {action}<br>Shares: {shares:,.0f}<br>"
                        f"Value: ${value:,.0f}K<br>Weight: {w:.2f}%"
                    )
                else:
                    hover_texts.at[fund, ticker] = f"Action: {action}"

    st.write(f"Displaying {len(pivot)} funds x {len(pivot.columns)} stocks")
    render_heatmap(pivot, f"Position Changes — {quarter}", hover_texts=hover_texts)

    with st.expander("View raw data"):
        display_df = df.sort_values(["fund_name", "action_code"], ascending=[True, False])
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_sector_heatmap(quarter: str, selected_fund_ids: list[int]) -> None:
    """模式 B: 板块权重热力图."""
    st.markdown("Color intensity = sector weight % (darker blue = higher allocation)")

    df = get_sector_weight_heatmap(quarter)
    if df.empty:
        st.info("No sector weight data available for this quarter.")
        return

    if selected_fund_ids:
        funds_df = get_funds_df()
        fund_names = funds_df[funds_df["fund_id"].isin(selected_fund_ids)]["name"].tolist()
        df = df[df["fund_name"].isin(fund_names)]

    if df.empty:
        st.info("No data after filtering.")
        return

    pivot = df.pivot_table(
        index="fund_name",
        columns="sector",
        values="weight_pct",
        aggfunc="first",
    ).fillna(0)

    st.write(f"Displaying {len(pivot)} funds x {len(pivot.columns)} sectors")

    fig = px.imshow(
        pivot,
        labels=dict(x="GICS Sector", y="Fund", color="Weight %"),
        x=pivot.columns,
        y=pivot.index,
        color_continuous_scale="Blues",
        aspect="auto",
        title=f"Sector Allocation — {quarter}",
    )
    fig.update_layout(
        height=max(600, len(pivot) * 18),
        xaxis_tickfont_size=10,
        yaxis_tickfont_size=10,
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View raw data"):
        st.dataframe(
            df.sort_values(["fund_name", "weight_pct"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )
