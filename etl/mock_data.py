"""
模拟数据生成器 —— 用于本地演示和测试（无需真实 API）
生成逼真的 13F 持仓数据
"""
import random
from datetime import date
from loguru import logger

from db.engine import get_session
from db.models import Fund, Filing, Holding, Security
from utils import date_to_quarter

# 模拟股票池 (CUSIP, Ticker, Name, GICS Sector)
MOCK_STOCKS = [
    ("037833100", "AAPL", "Apple Inc.", "Information Technology"),
    ("594918104", "MSFT", "Microsoft Corp.", "Information Technology"),
    ("67066G104", "NVDA", "NVIDIA Corp.", "Information Technology"),
    ("023135106", "AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    ("02079K107", "GOOGL", "Alphabet Inc.", "Communication Services"),
    ("30303M102", "META", "Meta Platforms Inc.", "Communication Services"),
    ("88160R101", "TSLA", "Tesla Inc.", "Consumer Discretionary"),
    ("084670702", "BRK-B", "Berkshire Hathaway", "Financials"),
    ("46625H100", "JPM", "JPMorgan Chase & Co.", "Financials"),
    ("92826C839", "V", "Visa Inc.", "Financials"),
    ("478160104", "JNJ", "Johnson & Johnson", "Health Care"),
    ("91324P102", "UNH", "UnitedHealth Group", "Health Care"),
    ("30231G102", "XOM", "Exxon Mobil Corp.", "Energy"),
    ("931142103", "WMT", "Walmart Inc.", "Consumer Staples"),
    ("742718109", "PG", "Procter & Gamble", "Consumer Staples"),
    ("57636Q104", "MA", "Mastercard Inc.", "Financials"),
    ("437076102", "HD", "Home Depot Inc.", "Consumer Discretionary"),
    ("532457108", "LLY", "Eli Lilly & Co.", "Health Care"),
    ("166764100", "CVX", "Chevron Corp.", "Energy"),
    ("58933Y105", "MRK", "Merck & Co.", "Health Care"),
    ("713448108", "PEP", "PepsiCo Inc.", "Consumer Staples"),
    ("22160K105", "COST", "Costco Wholesale", "Consumer Staples"),
    ("00287Y109", "ABBV", "AbbVie Inc.", "Health Care"),
    ("191216100", "KO", "Coca-Cola Co.", "Consumer Staples"),
    ("G017671104", "AVGO", "Broadcom Inc.", "Information Technology"),
    ("00724F101", "ADBE", "Adobe Inc.", "Information Technology"),
    ("79466L302", "CRM", "Salesforce Inc.", "Information Technology"),
    ("64110L106", "NFLX", "Netflix Inc.", "Communication Services"),
    ("883556102", "TMO", "Thermo Fisher Scientific", "Health Care"),
    ("007903107", "AMD", "Advanced Micro Devices", "Information Technology"),
]

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


async def generate_mock_holdings_for_fund(fund: Fund, report_date: date, seed: int = 42):
    """为单个基金生成某季度的模拟持仓"""
    rng = random.Random(seed + fund.fund_id + report_date.toordinal())
    
    # 每个基金持有 15-40 只股票
    num_holdings = rng.randint(15, 40)
    stocks = rng.sample(MOCK_STOCKS, min(num_holdings, len(MOCK_STOCKS)))
    
    holdings = []
    total_value = 0
    for cusip, ticker, name, sector in stocks:
        shares = rng.randint(10000, 5000000)
        price = rng.uniform(50, 500)
        value = int(shares * price / 1000)  # 千美元
        total_value += value
        holdings.append({
            "cusip": cusip,
            "ticker": ticker,
            "name": name,
            "shares": shares,
            "value": value,
            "put_call": None,
        })
    
    # 计算权重
    for h in holdings:
        h["weight_pct"] = round(h["value"] / total_value * 100, 4) if total_value > 0 else 0
    
    return holdings, total_value


async def seed_mock_data(quarters: int = 8):
    """为所有基金生成模拟数据并入库"""
    logger.info("Generating mock data for demonstration...")
    
    with get_session() as session:
        funds = session.query(Fund).filter(Fund.is_active == True).all()
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
            for q_idx, report_date in enumerate(quarter_dates):
                # 检查是否已存在
                existing = session.query(Filing).filter(
                    Filing.fund_id == fund.fund_id,
                    Filing.report_date == report_date,
                ).first()
                if existing:
                    continue
                
                holdings, total_value = await generate_mock_holdings_for_fund(fund, report_date, seed=42)
                
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
            
            logger.info(f"Mock data generated for {fund.name}")
        
        logger.info(f"Mock data seeding complete. Total holdings: {total_holdings}")
