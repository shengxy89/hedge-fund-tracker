"""Dashboard 数字格式化工具：货币、百分比、股数、Delta、Action 标签."""

from __future__ import annotations

from dashboard.theme import ACTION_COLORS

# =============================================================================
# 数字格式化
# =============================================================================


def format_currency(value: float | int | None, decimals: int = 1) -> str:
    """格式化金额 — 输入为 SEC 13F 原始单位（千美元）.

    分级规则（基于千美元）：
        >= 1,000,000 K → $X.XB  (十亿美元)
        >= 1,000 K     → $X.XM  (百万美元)
        其他           → $X.XK  (千美元)

    Args:
        value: 千美元金额.
        decimals: 小数位数.

    Returns:
        如 "$6.9B", "$123.5M", "$890.5K", "—".
    """
    if value is None or value != value:  # NaN check
        return "—"
    val = float(value)
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:,.{decimals}f}B"
    if abs(val) >= 1_000:
        return f"${val / 1_000:,.{decimals}f}M"
    if abs(val) < 0.01:
        return "$0K"
    return f"${val:,.{decimals}f}K"


def format_pct(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    """格式化为百分比.

    Args:
        value: 小数，如 0.123 表示 12.3%.
        decimals: 小数位数.
        signed: 是否强制显示正负号.

    Returns:
        如 "12.3%", "+5.6%", "—".
    """
    if value is None or value != value:
        return "—"
    fmt = f"{{:+.{decimals}f}}%" if signed else f"{{:.{decimals}f}}%"
    return fmt.format(value * 100)


def format_shares(value: int | float | None) -> str:
    """格式化股数为千分位.

    Args:
        value: 股数.

    Returns:
        如 "12,345,678", "—".
    """
    if value is None or value != value:
        return "—"
    return f"{int(value):,}"


def format_delta(
    value: float | None,
    decimals: int = 1,
    suffix: str = "",
    as_pct: bool = False,
) -> str:
    """格式化变化值，带颜色标记的 HTML span.

    Args:
        value: 变化数值.
        decimals: 小数位数.
        suffix: 后缀，如 '%' 或 'bps'.
        as_pct: 若 True，将 value 当作小数按百分比格式化.

    Returns:
        HTML span 字符串，如 '<span style="color:#2E7D32">+5.6%</span>'.
    """
    if value is None or value != value:
        return "—"

    if as_pct:
        text = format_pct(value, decimals=decimals, signed=True)
    else:
        sign = "+" if value > 0 else ""
        text = f"{sign}{value:,.{decimals}f}{suffix}"

    color = "#2E7D32" if value > 0 else "#C62828" if value < 0 else "#9E9E9E"
    return f'<span style="color:{color};font-weight:600;">{text}</span>'


# =============================================================================
# 标签 / 标识
# =============================================================================


def get_action_badge(action: str | None) -> str:
    """返回带 Emoji 的 Action 标签.

    Args:
        action: NEW / ADD / HOLD / REDUCE / SOLD.

    Returns:
        如 '🟢 NEW', '🔴 SOLD', '⚪ —'.
    """
    badges = {
        "NEW": "🟢 NEW",
        "ADD": "🟡 ADD",
        "HOLD": "⚪ HOLD",
        "REDUCE": "🔵 REDUCE",
        "SOLD": "🔴 SOLD",
    }
    return badges.get(action or "", "⚪ —")


def get_action_color(action: str | None) -> str:
    """返回 Action 对应的 Hex 颜色.

    Args:
        action: NEW / ADD / HOLD / REDUCE / SOLD.

    Returns:
        Hex 颜色字符串，默认中性灰.
    """
    return ACTION_COLORS.get(action or "", "#9E9E9E")


def display_label(ticker: str | None, name: str | None, max_name_len: int = 12) -> str:
    """生成展示标签：优先 ticker，无 ticker 时截取 name 前 N 字符.

    国际股（无 ticker）会在前面加 🌐.

    Args:
        ticker: 股票代码，可能为 None.
        name: 公司名称，可能为 None.
        max_name_len: name 最大显示长度.

    Returns:
        如 'AAPL', '🌐 ASML HOLDING', '—'.
    """
    if ticker:
        return ticker
    if name:
        truncated = name[:max_name_len] + ("…" if len(name) > max_name_len else "")
        return f"🌐 {truncated}"
    return "—"
