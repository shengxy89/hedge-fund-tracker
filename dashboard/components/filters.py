"""侧边栏筛选器组件 — 季度/基金/Sector/最小市值 多维筛选."""

from __future__ import annotations

import streamlit as st

from dashboard.data_access import get_available_quarters, get_funds_df


def render_sidebar() -> tuple[str | None, list[int], list[str], bool]:
    """渲染侧边栏筛选器，返回用户选择.

    Returns:
        (selected_quarter, selected_fund_ids, selected_sectors, refresh)
    """
    st.sidebar.title("13F Alpha Tracker")
    st.sidebar.markdown("---")

    # 初始化 session_state
    if "selected_quarter" not in st.session_state:
        st.session_state.selected_quarter = None
    if "selected_funds" not in st.session_state:
        st.session_state.selected_funds = []
    if "selected_sectors" not in st.session_state:
        st.session_state.selected_sectors = []

    quarters = get_available_quarters()
    if not quarters:
        st.sidebar.warning("No data available. Please run ETL first.")
        return None, [], [], False

    # 季度选择
    selected_quarter = st.sidebar.selectbox(
        "Select Quarter",
        options=quarters,
        index=0,
        key="sb_quarter",
    )
    st.session_state.selected_quarter = selected_quarter

    # 基金多选
    funds_df = get_funds_df()
    fund_options = dict(zip(funds_df["name"], funds_df["fund_id"]))
    selected_fund_names = st.sidebar.multiselect(
        "Select Funds (optional)",
        options=list(fund_options.keys()),
        default=st.session_state.selected_funds,
        key="sb_funds",
    )
    selected_fund_ids = [fund_options[name] for name in selected_fund_names]
    st.session_state.selected_funds = selected_fund_names

    # 板块筛选
    sectors = [
        "Information Technology",
        "Health Care",
        "Financials",
        "Consumer Discretionary",
        "Communication Services",
        "Industrials",
        "Consumer Staples",
        "Energy",
        "Utilities",
        "Real Estate",
        "Materials",
    ]
    selected_sectors = st.sidebar.multiselect(
        "Filter by Sector",
        options=sectors,
        default=st.session_state.selected_sectors,
        key="sb_sectors",
    )
    st.session_state.selected_sectors = selected_sectors

    # 刷新按钮
    refresh = st.sidebar.button("Refresh Data", use_container_width=True)

    # 重置按钮
    if st.sidebar.button("Reset Filters", use_container_width=True):
        st.session_state.selected_funds = []
        st.session_state.selected_sectors = []
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("Data source: SEC 13F Filings")
    st.sidebar.caption(
        "Note: SOLD may indicate position below disclosure threshold, "
        "not necessarily complete liquidation."
    )

    return selected_quarter, selected_fund_ids, selected_sectors, refresh
