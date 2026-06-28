"""免责声明与说明组件：SOLD 阈值、PUT/CALL、13F 延迟."""

from __future__ import annotations

import streamlit as st

# =============================================================================
# SOLD 免责声明
# =============================================================================


def sold_threshold_disclaimer(expanded: bool = False) -> None:
    """SOLD 可能为降至披露阈值以下的免责声明.

    Args:
        expanded: 是否默认展开详情.
    """
    with st.expander("ℹ️ 关于 SOLD / 清仓的说明", expanded=expanded):
        st.markdown(
            """
            **13F 披露阈值提醒**

            13F 报告仅要求披露超过一定门槛的持仓（通常约 **$25M** 或管理规模对应的阈值）。
            因此：

            - **SOLD** 标签表示该持仓在当前报告期中未出现，这可能意味着：
              1. 基金完全清仓该股票；
              2. 持仓降至披露阈值以下，但基金仍可能持有少量头寸；
              3. 股票被并购、退市或代码变更。

            - **NEW** 标签表示该持仓在上个报告期未出现，这可能意味着：
              1. 基金新建立了头寸；
              2. 持仓从阈值以下增至阈值以上。

            > 请以基金官方披露或 13F Amendment 为准。
            """
        )


# =============================================================================
# 数据延迟徽章
# =============================================================================


def filing_delay_badge(report_date: str | None, filing_date: str | None) -> None:
    """在页面顶部显示数据延迟状态徽章.

    Args:
        report_date: 持仓报告日期（季末）.
        filing_date: SEC 收到日期.
    """
    if not report_date or not filing_date:
        st.warning("⚠️ 数据延迟信息缺失")
        return

    from datetime import date

    try:
        rd = date.fromisoformat(str(report_date))
        fd = date.fromisoformat(str(filing_date))
        lag_days = (fd - rd).days
    except ValueError:
        st.warning("⚠️ 日期格式异常")
        return

    if lag_days <= 0:
        st.success(f"✅ Data as of {report_date}")
    elif lag_days <= 50:
        st.info(
            f"📅 Data as of **{report_date}** · Filed **{filing_date}** · "
            f"Lag **{lag_days} days** (within normal 13F window)"
        )
    else:
        st.warning(
            f"⏰ Data as of **{report_date}** · Filed **{filing_date}** · "
            f"Lag **{lag_days} days** (longer than typical 45-day window)"
        )
