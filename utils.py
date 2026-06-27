from calendar import monthrange
from datetime import date


def date_to_quarter(d: date) -> str:
    """将日期转换为季度格式，如 2024-09-30 → '2024Q3'"""
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def quarter_to_dates(quarter: str) -> tuple[date, date]:
    """将季度格式转换为 (开始日期, 结束日期)
    例如 '2024Q3' → (2024-07-01, 2024-09-30)
    """
    year = int(quarter[:4])
    q = int(quarter[-1])
    start_month = (q - 1) * 3 + 1
    end_month = q * 3
    end_day = monthrange(year, end_month)[1]
    return date(year, start_month, 1), date(year, end_month, end_day)


def pad_cik(cik: str | int) -> str:
    """CIK 补零到 10 位"""
    return str(cik).zfill(10)


def get_prev_quarter(quarter: str) -> str:
    """获取上一个季度，如 '2024Q1' → '2023Q4'"""
    year = int(quarter[:4])
    q = int(quarter[-1])
    if q == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{q - 1}"


def quarter_date_range(quarter: str) -> tuple[date, date]:
    """返回季度的日期范围，等价于 quarter_to_dates"""
    return quarter_to_dates(quarter)
