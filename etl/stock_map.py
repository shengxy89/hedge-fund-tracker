"""统一的内置股票映射（CUSIP / Ticker / Name / GICS Sector / Industry）。

Mock 数据生成器与 CUSIP resolver 共享同一份映射，避免两处维护不一致。

数据来源：S&P 500 常见成分股（手工整理），用于：
- mock_data：生成演示持仓
- cusip_resolver：缺失 ticker 时静态回填 sector/industry
"""
from __future__ import annotations

# (CUSIP, Ticker, Name, GICS Sector, GICS Industry)
STOCK_MAP: tuple[tuple[str, str, str, str, str], ...] = (
    ("037833100", "AAPL",  "Apple Inc.",                 "Information Technology", "Technology Hardware, Storage & Peripherals"),
    ("594918104", "MSFT",  "Microsoft Corp.",            "Information Technology", "Systems Software"),
    ("67066G104", "NVDA",  "NVIDIA Corp.",               "Information Technology", "Semiconductors"),
    ("023135106", "AMZN",  "Amazon.com Inc.",            "Consumer Discretionary", "Broadline Retail"),
    ("02079K107", "GOOGL", "Alphabet Inc.",              "Communication Services", "Interactive Media & Services"),
    ("02079K106", "GOOG",  "Alphabet Inc. (C)",          "Communication Services", "Interactive Media & Services"),
    ("30303M102", "META",  "Meta Platforms Inc.",        "Communication Services", "Interactive Media & Services"),
    ("88160R101", "TSLA",  "Tesla Inc.",                 "Consumer Discretionary", "Automobiles"),
    ("084670702", "BRK-B", "Berkshire Hathaway (B)",     "Financials",             "Multi-Sector Holdings"),
    ("46625H100", "JPM",   "JPMorgan Chase & Co.",       "Financials",             "Diversified Banks"),
    ("92826C839", "V",     "Visa Inc.",                  "Financials",             "Transaction & Payment Processing Services"),
    ("478160104", "JNJ",   "Johnson & Johnson",          "Health Care",            "Pharmaceuticals"),
    ("91324P102", "UNH",   "UnitedHealth Group",         "Health Care",            "Managed Health Care"),
    ("30231G102", "XOM",   "Exxon Mobil Corp.",          "Energy",                 "Integrated Oil & Gas"),
    ("931142103", "WMT",   "Walmart Inc.",               "Consumer Staples",       "Consumer Staples Merchandise Retail"),
    ("742718109", "PG",    "Procter & Gamble",           "Consumer Staples",       "Personal Care Products"),
    ("57636Q104", "MA",    "Mastercard Inc.",            "Financials",             "Transaction & Payment Processing Services"),
    ("437076102", "HD",    "Home Depot Inc.",            "Consumer Discretionary", "Home Improvement Retail"),
    ("532457108", "LLY",   "Eli Lilly & Co.",            "Health Care",            "Pharmaceuticals"),
    ("166764100", "CVX",   "Chevron Corp.",              "Energy",                 "Integrated Oil & Gas"),
    ("58933Y105", "MRK",   "Merck & Co.",                "Health Care",            "Pharmaceuticals"),
    ("713448108", "PEP",   "PepsiCo Inc.",               "Consumer Staples",       "Soft Drinks & Non-alcoholic Beverages"),
    ("22160K105", "COST",  "Costco Wholesale",           "Consumer Staples",       "Consumer Staples Merchandise Retail"),
    ("00287Y109", "ABBV",  "AbbVie Inc.",                "Health Care",            "Biotechnology"),
    ("191216100", "KO",    "Coca-Cola Co.",              "Consumer Staples",       "Soft Drinks & Non-alcoholic Beverages"),
    ("G017671104", "AVGO", "Broadcom Inc.",              "Information Technology", "Semiconductors"),
    ("00724F101", "ADBE",  "Adobe Inc.",                 "Information Technology", "Application Software"),
    ("79466L302", "CRM",   "Salesforce Inc.",            "Information Technology", "Application Software"),
    ("64110L106", "NFLX",  "Netflix Inc.",               "Communication Services", "Movies & Entertainment"),
    ("883556102", "TMO",   "Thermo Fisher Scientific",   "Health Care",            "Life Sciences Tools & Services"),
    ("007903107", "AMD",   "Advanced Micro Devices",     "Information Technology", "Semiconductors"),
    ("ACN",       "ACN",   "Accenture",                  "Information Technology", "IT Consulting & Other Services"),
    ("LIN",       "LIN",   "Linde plc",                  "Materials",              "Industrial Gases"),
    ("DIS",       "DIS",   "Walt Disney Co.",            "Communication Services", "Movies & Entertainment"),
    ("VZ",        "VZ",    "Verizon Communications",     "Communication Services", "Integrated Telecommunication Services"),
    ("INTC",      "INTC",  "Intel Corp.",                "Information Technology", "Semiconductors"),
    ("QCOM",      "QCOM",  "Qualcomm Inc.",              "Information Technology", "Semiconductors"),
    ("TXN",       "TXN",   "Texas Instruments",          "Information Technology", "Semiconductors"),
    ("NKE",       "NKE",   "Nike Inc.",                  "Consumer Discretionary", "Apparel, Accessories & Luxury Goods"),
    ("INTU",      "INTU",  "Intuit Inc.",                "Information Technology", "Application Software"),
    ("HON",       "HON",   "Honeywell International",    "Industrials",            "Industrial Conglomerates"),
    ("AMGN",      "AMGN",  "Amgen Inc.",                 "Health Care",            "Biotechnology"),
    ("LOW",       "LOW",   "Lowe's Companies",           "Consumer Discretionary", "Home Improvement Retail"),
)

# (ticker, sector, industry) — cusip_resolver 用
TICKER_TO_SECTOR: dict[str, tuple[str, str]] = {
    ticker: (sector, industry)
    for _cusip, ticker, _name, sector, industry in STOCK_MAP
}

# (cusip, ticker, name, sector) — mock_data 用（向后兼容旧签名）
MOCK_STOCKS: list[tuple[str, str, str, str]] = [
    (cusip, ticker, name, sector)
    for cusip, ticker, name, sector, _industry in STOCK_MAP
]
