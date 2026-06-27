"""
模拟数据生成器 —— 用于本地演示和测试（无需真实 API）
生成逼真的 13F 持仓数据
"""
import random
from datetime import date

from loguru import logger

from db.engine import get_session
from db.models import Filing, Fund, Holding, Security
from etl.stock_map import MOCK_STOCKS

# 模拟股票池 (CUSIP, Ticker, Name, GICS Sector) — 来自 etl/stock_map 统一映射


# 生成最近 8 个季度的季末日期
def get_recent_quarter_end_dates(n: int = 8) -> list[date]:
    """返回最近 n 个季度的季末日期（从最近一个完整季度往前推）"""
    today = date.today()
    # 找到当前所在季度的上一个季末
    quarter = (today.month - 1) // 3
    year = today.year
    # 上个季度的季末
    if quarter == 0:
        prev_q_end = date(year - 1, 12, 31)
    else:
        month_end = quarter * 3
        if month_end == 3:
            prev_q_end = date(year, 3, 31)
        elif month_end == 6:
            prev_q_end = date(year, 6, 30)
        elif month_end == 9:
            prev_q_end = date(year, 9, 30)
        else:
            prev_q_end = date(year, 12, 31)

    dates = []
    d = prev_q_end
    for _ in range(n):
        dates.append(d)
        # 上一个季度
        if d.month == 3:
            d = date(d.year - 1, 12, 31)
        elif d.month == 6:
            d = date(d.year, 3, 31)
        elif d.month == 9:
            d = date(d.year, 6, 30)
        else:
            d = date(d.year, 9, 30)
    return dates


async def generate_mock_holdings_for_fund(
    fund: Fund,
    report_date: date,
    seed: int = 42,
    prev_holdings: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """为单个基金生成某季度的模拟持仓。

    Markov 持仓演化模型（让相邻季度的数据具备连续性，使 delta 分析有意义）：
    - 若 prev_holdings 为 None（首季）：随机采样 15-40 只股票作为初始持仓
    - 否则：保留 ~80% 旧仓位（部分做 ADD/REDUCE 微调），新进 ~10% 仓位，
      清仓 ~10% 旧仓位

    Args:
        prev_holdings: 上一季度的持仓列表（dict 列表），None 表示首季。
    """
    rng = random.Random(seed + fund.fund_id + report_date.toordinal())

    def _make_holding(cusip_ticker_name_sector, shares: int, value: int) -> dict:
        cusip, ticker, name, _ = cusip_ticker_name_sector
        return {
            "cusip": cusip, "ticker": ticker, "name": name,
            "shares": shares, "value": value, "put_call": None,
        }

    if not prev_holdings:
        # 首季：随机采样 15-40 只股票
        num_holdings = rng.randint(15, 40)
        stocks = rng.sample(MOCK_STOCKS, min(num_holdings, len(MOCK_STOCKS)))
        holdings = []
        total_value = 0
        for stock in stocks:
            shares = rng.randint(10000, 5000000)
            price = rng.uniform(50, 500)
            value = int(shares * price / 1000)  # 千美元
            total_value += value
            holdings.append(_make_holding(stock, shares, value))
    else:
        # 演化：保留 80%、清仓 10%、新进 10%（按仓位数量计算，最少各 1 个）
        n_prev = len(prev_holdings)
        n_keep = max(1, int(n_prev * 0.8))
        n_drop = max(1, int(n_prev * 0.1))
        n_new = max(1, int(n_prev * 0.1))

        rng.shuffle(prev_holdings)
        keep = prev_holdings[:n_keep]
        dropped = prev_holdings[n_keep:n_keep + n_drop]
        _ = dropped  # 仅用于语义清晰：被清仓

        # 已持仓的 CUSIP 集合，避免新进重复
        kept_cusips = {h["cusip"] for h in keep}
        new_candidates = [s for s in MOCK_STOCKS if s[0] not in kept_cusips]
        new_stocks = rng.sample(new_candidates, min(n_new, len(new_candidates)))

        holdings = []
        total_value = 0
        # 保留仓位：70% 不变、20% ADD、10% REDUCE
        for h in keep:
            roll = rng.random()
            old_shares = h["shares"]
            old_value = h["value"]
            if roll < 0.70:
                shares, value = old_shares, old_value
            elif roll < 0.90:  # ADD 5%-50%
                mult = rng.uniform(1.05, 1.50)
                shares = int(old_shares * mult)
                value = int(old_value * mult)
            else:  # REDUCE 30%-70%
                mult = rng.uniform(0.30, 0.70)
                shares = int(old_shares * mult)
                value = int(old_value * mult)
            # 找回 stock 元组
            stock = next((s for s in MOCK_STOCKS if s[0] == h["cusip"]), None)
            if stock is None:
                continue
            holdings.append(_make_holding(stock, shares, value))
            total_value += value

        # 新进仓位
        for stock in new_stocks:
            shares = rng.randint(10000, 5000000)
            price = rng.uniform(50, 500)
            value = int(shares * price / 1000)
            holdings.append(_make_holding(stock, shares, value))
            total_value += value

    # 计算权重
    for h in holdings:
        h["weight_pct"] = round(h["value"] / total_value * 100, 4) if total_value > 0 else 0

    return holdings, total_value


async def seed_mock_data(quarters: int = 8):
    """为所有基金生成模拟数据并入库。

    使用 Markov 持仓演化：每个基金的首季随机生成，后续季度从上一季度的
    持仓演化而来（保留 / 加减 / 清仓 / 新建），使 delta_engine 能产生
    合理的 NEW/ADD/REDUCE/SOLD 分布。
    """
    logger.info("Generating mock data for demonstration...")

    with get_session() as session:
        funds = session.query(Fund).filter(Fund.is_active.is_(True)).all()
        if not funds:
            logger.warning("No funds found. Please run seed_funds.py first.")
            return

        # 预写入 securities
        for cusip, ticker, name, sector in MOCK_STOCKS:
            existing = session.query(Security).filter(Security.cusip == cusip).first()
            if not existing:
                sec = Security(cusip=cusip, ticker=ticker, name=name, sector=sector)
                session.add(sec)

        quarter_dates = get_recent_quarter_end_dates(quarters)
        logger.info(f"Quarter dates: {[d.isoformat() for d in quarter_dates]}")

        total_holdings = 0
        for fund in funds:
            prev_holdings: list[dict] | None = None
            for q_idx, report_date in enumerate(quarter_dates):
                # 检查是否已存在
                existing = session.query(Filing).filter(
                    Filing.fund_id == fund.fund_id,
                    Filing.report_date == report_date,
                ).first()
                if existing:
                    # 已有数据，从 DB 读出作为下一季的 prev
                    prev_holdings = [
                        {"cusip": h.cusip, "ticker": h.ticker, "name": h.name,
                         "shares": h.shares, "value": h.value}
                        for h in session.query(Holding).filter(
                            Holding.fund_id == fund.fund_id,
                            Holding.report_date == report_date,
                        ).all()
                    ]
                    continue

                holdings, total_value = await generate_mock_holdings_for_fund(
                    fund, report_date, seed=42, prev_holdings=prev_holdings,
                )

                # 创建 filing 记录
                acc_num = f"{fund.cik}-{report_date.strftime('%Y%m%d')}"
                filing = Filing(
                    fund_id=fund.fund_id,
                    accession_number=acc_num,
                    filing_date=report_date,
                    report_date=report_date,
                    form_type="13F-HR",
                    is_amendment=False,
                    total_value=total_value,
                    holding_count=len(holdings),
                )
                session.add(filing)
                session.flush()

                for h in holdings:
                    holding = Holding(
                        fund_id=fund.fund_id,
                        report_date=report_date,
                        cusip=h["cusip"],
                        ticker=h["ticker"],
                        name=h["name"],
                        shares=h["shares"],
                        value=h["value"],
                        weight_pct=h["weight_pct"],
                        put_call=h["put_call"],
                    )
                    session.add(holding)
                    total_holdings += 1

                # 当前季度的 holdings 作为下一季的 prev
                prev_holdings = holdings

            logger.info(f"Mock data generated for {fund.name}")

        logger.info(f"Mock data seeding complete. Total holdings: {total_holdings}")
