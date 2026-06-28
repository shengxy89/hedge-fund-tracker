"""全局时间窗口辅助：读取侧边栏历史范围，返回时序图用的季度列表."""

from __future__ import annotations

import streamlit as st

from dashboard.data_access import get_available_quarters

DEFAULT_HISTORY_N: int = 8


def get_history_quarters(n: int | None = None) -> list[str]:
    """返回最近 N 个季度（降序，最新在前）。

    n 为 None 时读 session_state.history_n（侧边栏滑块），默认 8。
    """
    if n is None:
        n = st.session_state.get("history_n", DEFAULT_HISTORY_N)
    quarters = get_available_quarters()  # 已是降序
    return quarters[:n]


def get_history_quarters_ascending(n: int | None = None) -> list[str]:
    """返回最近 N 个季度（升序，最旧在前，适合时序折线图）."""
    return list(reversed(get_history_quarters(n)))
