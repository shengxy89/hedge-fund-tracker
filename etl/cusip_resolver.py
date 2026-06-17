"""
CUSIP -> Ticker / Sector 解析模块
支持批量查询以优化 OpenFIGI 速率限制
"""
import asyncio
from typing import Optional

import httpx
from loguru import logger

from config.settings import get_settings
from db.engine import get_session
from db.models import Security
from etl.stock_map import TICKER_TO_SECTOR as BUILTIN_SECTOR_MAP

settings = get_settings()

# 进程级内存缓存，避免同一批次内重复查询
_memory_cache: dict[str, dict] = {}

# 内置 S&P 500 sector 映射来自 etl/stock_map.TICKER_TO_SECTOR（统一来源）



async def _openfigi_request(payload: list[dict]) -> list[dict]:
    """向 OpenFIGI 发送批量请求，自带限速重试"""
    url = "https://api.openfigi.com/v3/mapping"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.debug(f"OpenFIGI rate limited, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.debug(f"OpenFIGI request failed (attempt {attempt + 1}): {e}")
            await asyncio.sleep(1)
    return []


async def resolve_from_openfigi(cusip: str) -> Optional[tuple[str, str]]:
    """使用 OpenFIGI API 解析单个 CUSIP -> (ticker, name)"""
    results = await resolve_from_openfigi_batch([cusip])
    return results.get(cusip)


async def resolve_from_openfigi_batch(cusips: list[str]) -> dict[str, tuple[str, str]]:
    """
    批量使用 OpenFIGI API 解析 CUSIP -> {cusip: (ticker, name)}
    OpenFIGI 批量限制：每次最多 100 个，每分钟最多 25 个请求
    实际使用中 batch_size=25 以避免 413 Payload Too Large
    """
    result: dict[str, tuple[str, str]] = {}
    if not cusips:
        return result

    # 分批处理，每批 10 个（OpenFIGI 免费版限制）
    batch_size = 10
    for i in range(0, len(cusips), batch_size):
        batch = cusips[i : i + batch_size]
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        data = await _openfigi_request(payload)

        for item, cusip in zip(data, batch):
            if "data" in item and len(item["data"]) > 0:
                d = item["data"][0]
                result[cusip] = (d.get("ticker", ""), d.get("name", ""))
            elif "warning" in item:
                logger.debug(f"OpenFIGI warning for {cusip}: {item['warning']}")

        # 批次间限速：每分钟 25 请求 ≈ 2.4s/请求
        if i + batch_size < len(cusips):
            await asyncio.sleep(2.5)

    return result


async def resolve_from_fmp(ticker: str) -> Optional[tuple[str, str]]:
    """使用 FMP API 获取 sector/industry"""
    if not settings.fmp_api_key:
        return None
    url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={settings.fmp_api_key}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data and len(data) > 0:
                profile = data[0]
                return profile.get("sector", ""), profile.get("industry", "")
    except Exception as e:
        logger.debug(f"FMP failed for {ticker}: {e}")
    return None


def get_security_from_db(cusip: str) -> Optional[dict]:
    """查询本地 securities 表缓存，返回 plain dict（避免 DetachedInstanceError）"""
    with get_session(read_only=True) as session:
        sec = session.query(Security).filter(Security.cusip == cusip).first()
        if sec is None:
            return None
        return {
            "cusip": sec.cusip,
            "ticker": sec.ticker,
            "name": sec.name,
            "sector": sec.sector,
            "industry": sec.industry,
        }


def save_security_to_db(cusip: str, ticker: Optional[str], name: Optional[str],
                        sector: Optional[str], industry: Optional[str]) -> None:
    """写入 securities 表作为缓存"""
    with get_session() as session:
        existing = session.query(Security).filter(Security.cusip == cusip).first()
        if existing:
            if ticker:
                existing.ticker = ticker
            if name:
                existing.name = name
            if sector:
                existing.sector = sector
            if industry:
                existing.industry = industry
        else:
            sec = Security(
                cusip=cusip,
                ticker=ticker,
                name=name,
                sector=sector,
                industry=industry,
            )
            session.add(sec)


async def resolve_cusip(cusip: str, prefilled_ticker: Optional[str] = None,
                        prefilled_name: Optional[str] = None) -> dict:
    """
    解析单个 CUSIP，返回 {"cusip", "ticker", "name", "sector", "industry"}
    """
    # 内存缓存命中直接返回
    if cusip in _memory_cache:
        cached = _memory_cache[cusip].copy()
        if prefilled_ticker:
            cached["ticker"] = prefilled_ticker
        if prefilled_name:
            cached["name"] = prefilled_name
        return cached

    result = {
        "cusip": cusip,
        "ticker": prefilled_ticker,
        "name": prefilled_name,
        "sector": None,
        "industry": None,
    }

    ticker = prefilled_ticker
    name = prefilled_name

    # 本地 DB 缓存
    if not ticker:
        cached = get_security_from_db(cusip)
        if cached:
            ticker = cached.get("ticker")
            name = cached.get("name")
            result["sector"] = cached.get("sector")
            result["industry"] = cached.get("industry")

    # OpenFIGI
    if not ticker:
        figi = await resolve_from_openfigi(cusip)
        if figi:
            ticker, name = figi

    # 内置映射
    if ticker and ticker.upper() in BUILTIN_SECTOR_MAP:
        sector, industry = BUILTIN_SECTOR_MAP[ticker.upper()]
        result["sector"] = sector or result["sector"]
        result["industry"] = industry or result["industry"]

    # FMP 补充 sector
    if ticker and not result["sector"]:
        fmp = await resolve_from_fmp(ticker)
        if fmp:
            result["sector"], result["industry"] = fmp

    result["ticker"] = ticker
    result["name"] = name

    # 写入缓存
    if ticker or name:
        save_security_to_db(cusip, ticker, name, result["sector"], result["industry"])

    _memory_cache[cusip] = result.copy()
    return result


async def resolve_cusips_batch(cusips: list[str]) -> dict[str, dict]:
    """
    批量解析 CUSIP，返回 {cusip: {"cusip", "ticker", "name", "sector", "industry"}}
    优先使用内存缓存和 DB，缺失的批量调用 OpenFIGI
    """
    result: dict[str, dict] = {}
    missing: list[str] = []

    for cusip in cusips:
        if not cusip:
            continue
        if cusip in _memory_cache:
            result[cusip] = _memory_cache[cusip].copy()
            continue
        db_cached = get_security_from_db(cusip)
        if db_cached and db_cached.get("ticker"):
            result[cusip] = db_cached
            _memory_cache[cusip] = db_cached.copy()
            continue
        missing.append(cusip)

    if missing:
        figi_results = await resolve_from_openfigi_batch(missing)
        for cusip in missing:
            ticker, name = figi_results.get(cusip, (None, None))
            # 内置映射
            sector, industry = None, None
            if ticker and ticker.upper() in BUILTIN_SECTOR_MAP:
                sector, industry = BUILTIN_SECTOR_MAP[ticker.upper()]
            # FMP
            if ticker and not sector:
                fmp = await resolve_from_fmp(ticker)
                if fmp:
                    sector, industry = fmp

            info = {
                "cusip": cusip,
                "ticker": ticker,
                "name": name,
                "sector": sector,
                "industry": industry,
            }
            if ticker or name:
                save_security_to_db(cusip, ticker, name, sector, industry)
            _memory_cache[cusip] = info.copy()
            result[cusip] = info

    return result
