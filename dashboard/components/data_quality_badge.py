"""数据质量徽章组件：覆盖率标识、国际股标签、延迟状态."""

from __future__ import annotations

import streamlit as st

# =============================================================================
# 覆盖率徽章
# =============================================================================


def coverage_badge(
    total: int,
    with_ticker: int,
    with_sector: int,
) -> None:
    """显示数据覆盖率徽章.

    Args:
        total: 总记录数.
        with_ticker: 有 ticker 的记录数.
        with_sector: 有 sector 的记录数.
    """
    if total == 0:
        st.warning("⚠️ 暂无持仓数据")
        return

    ticker_pct = with_ticker / total * 100
    sector_pct = with_sector / total * 100

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Holdings", f"{total:,}")
    with col2:
        st.metric("Ticker Coverage", f"{ticker_pct:.1f}%", help=f"{with_ticker:,} / {total:,}")
    with col3:
        st.metric("Sector Coverage", f"{sector_pct:.1f}%", help=f"{with_sector:,} / {total:,}")

    if ticker_pct < 90:
        st.info(
            f"🌐 **{100 - ticker_pct:.1f}%** 持仓无 Ticker（多为国际股 ADR），"
            "已自动用 name 兜底显示。"
        )


# =============================================================================
# 国际股标签
# =============================================================================


def international_stock_label(ticker: str | None, name: str | None) -> str:
    """返回国际股展示标签.

    Args:
        ticker: 股票代码，可能为 None.
        name: 公司名称.

    Returns:
        如 'AAPL', '🌐 ASML HOLDING'.
    """
    if ticker and str(ticker).strip():
        return str(ticker)
    if name:
        truncated = name[:12] + ("…" if len(name) > 12 else "")
        return f"🌐 {truncated}"
    return "—"


def id_type_badge(ticker: str | None) -> str:
    """返回 ID 类型标识.

    Args:
        ticker: 股票代码.

    Returns:
        '🌐 NAME-only' 或 '🇺🇸 TICKER'.
    """
    if ticker and str(ticker).strip():
        return "🇺🇸 TICKER"
    return "🌐 NAME-only"


# =============================================================================
# 数据新鲜度
# =============================================================================


def data_freshness_badge(
    latest_report_date: str | None,
    latest_filing_date: str | None,
) -> None:
    """显示数据新鲜度状态.

    Args:
        latest_report_date: 最新持仓报告日期.
        latest_filing_date: 最新 SEC 收到日期.
    """
    if not latest_report_date:
        st.error("❌ 无可用数据 — 请先运行 ETL")
        return

    st.success(f"✅ 最新数据: {latest_report_date} (Filed: {latest_filing_date or 'N/A'})")
