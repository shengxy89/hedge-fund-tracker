"""
13F 数据抓取模块
支持 forms13f.com API 和 SEC EDGAR 双数据源
"""
import asyncio
import json
from datetime import date, timedelta
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from config.settings import get_settings
from utils import pad_cik, date_to_quarter

settings = get_settings()


class RateLimiter:
    """异步速率限制器"""
    def __init__(self, delay_sec: float):
        self.delay = delay_sec
        self._last_call: Optional[float] = None

    async def acquire(self):
        if self._last_call is not None:
            elapsed = asyncio.get_event_loop().time() - self._last_call
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
        self._last_call = asyncio.get_event_loop().time()


rate_limiter = RateLimiter(settings.rate_limit_delay)


@retry(stop=stop_after_attempt(settings.max_retries), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _get(url: str, headers: Optional[dict] = None, client: Optional[httpx.AsyncClient] = None) -> dict:
    """带重试的 GET 请求"""
    await rate_limiter.acquire()
    default_headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept": "application/json",
    }
    if headers:
        default_headers.update(headers)

    c = client or httpx.AsyncClient(timeout=30)
    try:
        resp = await c.get(url, headers=default_headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} for {url}")
        raise
    except Exception as e:
        logger.warning(f"Request error for {url}: {e}")
        raise
    finally:
        if client is None:
            await c.aclose()


async def fetch_filings_forms13f(cik: str, quarters: int = 8, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """
    从 forms13f.com API 获取指定基金的 filings 列表
    返回最近 {quarters} 个季度的 13F-HR / 13F-HR/A 记录
    """
    base = settings.forms13f_api_base.rstrip("/")
    url = f"{base}/filings?cik={cik}"
    try:
        data = await _get(url, client=client)
        filings = data if isinstance(data, list) else data.get("filings", [])
        # 过滤 13F-HR 相关
        filings = [f for f in filings if "13F-HR" in f.get("form_type", "")]
        # 按 report_date 降序，取最近 quarters 个
        filings.sort(key=lambda x: x.get("report_date", ""), reverse=True)
        return filings[:quarters]
    except Exception as e:
        logger.error(f"forms13f API failed for CIK {cik}: {e}")
        return []


async def fetch_holdings_forms13f(accession_number: str, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """从 forms13f.com API 获取单个 filing 的持仓明细"""
    base = settings.forms13f_api_base.rstrip("/")
    url = f"{base}/filings/{accession_number}/holdings"
    try:
        data = await _get(url, client=client)
        return data if isinstance(data, list) else data.get("holdings", [])
    except Exception as e:
        logger.error(f"forms13f holdings API failed for {accession_number}: {e}")
        return []


async def fetch_filings_sec(cik: str, quarters: int = 8, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """
    从 SEC EDGAR 获取 filings 列表（备用数据源）
    https://efts.sec.gov/LATEST/submissions/CIK{cik_padded}.json
    """
    padded = pad_cik(cik)
    url = f"{settings.sec_api_base}/submissions/CIK{padded}.json"
    try:
        data = await _get(url, client=client)
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        f_dates = recent.get("filingDate", [])
        r_dates = recent.get("reportDate", [])

        filings = []
        for form, acc, fd, rd in zip(forms, accs, f_dates, r_dates):
            if "13F-HR" not in form:
                continue
            filings.append({
                "accession_number": acc.replace("-", ""),
                "filing_date": fd,
                "report_date": rd,
                "form_type": form,
                "is_amendment": "/A" in form,
            })
        # 去重并按 report_date 降序
        seen = set()
        unique = []
        for f in filings:
            key = (f["accession_number"], f["report_date"])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        unique.sort(key=lambda x: x.get("report_date", ""), reverse=True)
        return unique[:quarters]
    except Exception as e:
        logger.error(f"SEC EDGAR failed for CIK {cik}: {e}")
        return []


async def fetch_holdings_sec(cik: str, accession_number: str, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """
    从 SEC EDGAR XML 获取持仓明细
    SEC 13F 的 holdings 通常位于 submission 目录下的某个 XML 文件中
    （常见文件名：infotable.xml 或 <number>.xml）
    """
    import re

    acc_no_dash = accession_number.replace("-", "")
    base_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dash}"
    await rate_limiter.acquire()
    c = client or httpx.AsyncClient(timeout=30)

    async def _try_fetch(url: str) -> str:
        resp = await c.get(url, headers={"User-Agent": settings.sec_user_agent})
        if resp.status_code == 200:
            return resp.text
        return ""

    try:
        def _has_info_table(text: str) -> bool:
            """检测 XML 是否包含 infoTable（支持 default ns 和 prefixed ns）"""
            if not text:
                return False
            return "<infoTable>" in text or "<ns1:infoTable>" in text or ":infoTable>" in text

        # 1. 尝试常见的 infotable.xml
        xml_text = await _try_fetch(f"{base_url}/infotable.xml")

        # 2. 尝试 primary_doc.xml（某些旧版 filing 的 holdings 在其中）
        if not _has_info_table(xml_text):
            xml_text = await _try_fetch(f"{base_url}/primary_doc.xml")

        # 3. 如果仍然没有找到 infoTable，从目录列表中查找其他 XML 文件
        if not _has_info_table(xml_text):
            dir_resp = await c.get(f"{base_url}/", headers={"User-Agent": settings.sec_user_agent})
            if dir_resp.status_code == 200:
                # 提取所有 .xml 链接（排除 primary_doc.xml）
                links = re.findall(r'href="([^"]+\.xml)"', dir_resp.text)
                for link in links:
                    if "primary_doc" in link:
                        continue
                    # 构建完整 URL（相对链接补全为 base_url + link）
                    if link.startswith("http"):
                        xml_url = link
                    elif link.startswith("/"):
                        xml_url = f"https://www.sec.gov{link}"
                    else:
                        xml_url = f"{base_url}/{link}"
                    xml_text = await _try_fetch(xml_url)
                    if _has_info_table(xml_text):
                        break

        if _has_info_table(xml_text):
            from etl.parser import parse_sec_13f_xml
            return parse_sec_13f_xml(xml_text)

        logger.warning(f"No holdings XML found for {accession_number}")
        return []
    except Exception as e:
        logger.error(f"SEC holdings fetch failed for {accession_number}: {e}")
        return []
    finally:
        if client is None:
            await c.aclose()


async def fetch_fund_data(cik: str, quarters: int = 8, skip_forms13f: bool = True) -> dict:
    """
    获取单个基金的所有数据
    返回: {
        "cik": str,
        "filings": list[dict],
        "holdings": dict[report_date, list[dict]]
    }
    """
    async with httpx.AsyncClient(timeout=30) as client:
        # forms13f.com API 当前不可用，直接跳过
        if skip_forms13f:
            filings = await fetch_filings_sec(cik, quarters, client=client)
            source = "sec"
        else:
            filings = await fetch_filings_forms13f(cik, quarters, client=client)
            source = "forms13f"
            if not filings:
                filings = await fetch_filings_sec(cik, quarters, client=client)
                source = "sec"

        holdings_map = {}
        for filing in filings:
            acc = filing.get("accession_number")
            r_date = filing.get("report_date")
            if not acc or not r_date:
                continue
            if source == "forms13f":
                h = await fetch_holdings_forms13f(acc, client=client)
            else:
                h = await fetch_holdings_sec(cik, acc, client=client)
            if h:
                holdings_map[r_date] = h

        return {
            "cik": cik,
            "filings": filings,
            "holdings": holdings_map,
            "source": source,
        }
