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
    """异步速率限制器（协程安全）"""
    def __init__(self, delay_sec: float):
        self.delay = delay_sec
        self._last_call: Optional[float] = None
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            loop = asyncio.get_event_loop()
            if self._last_call is not None:
                elapsed = loop.time() - self._last_call
                if elapsed < self.delay:
                    await asyncio.sleep(self.delay - elapsed)
            self._last_call = loop.time()


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


@retry(stop=stop_after_attempt(settings.max_retries), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _try_fetch_xml(client: httpx.AsyncClient, url: str) -> str:
    """带重试的 XML 抓取，仅 200 且非空才返回内容。"""
    await rate_limiter.acquire()
    resp = await client.get(url, headers={"User-Agent": settings.sec_user_agent})
    if resp.status_code == 200 and resp.text:
        return resp.text
    # 让 tenacity 看到「失败」就走重试：抛 HTTPStatusError
    raise httpx.HTTPStatusError(
        f"status={resp.status_code} for {url}", request=resp.request, response=resp
    )


async def fetch_holdings_sec(cik: str, accession_number: str, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """
    从 SEC EDGAR XML 获取持仓明细
    SEC 13F 的 holdings 通常位于 submission 目录下的某个 XML 文件中
    （常见文件名：infotable.xml 或 <number>.xml）
    """
    import re

    acc_no_dash = accession_number.replace("-", "")
    base_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dash}"

    owns_client = client is None
    c = client or httpx.AsyncClient(timeout=30)

    def _has_info_table(text: str) -> bool:
        """检测 XML 是否包含 infoTable（支持 default ns 和 prefixed ns）"""
        if not text:
            return False
        return "<infoTable>" in text or "<ns1:infoTable>" in text or ":infoTable>" in text

    try:
        # 1. 尝试常见的 infotable.xml
        try:
            xml_text = await _try_fetch_xml(c, f"{base_url}/infotable.xml")
        except httpx.HTTPError:
            xml_text = ""

        # 2. 尝试 primary_doc.xml（某些旧版 filing 的 holdings 在其中）
        if not _has_info_table(xml_text):
            try:
                xml_text = await _try_fetch_xml(c, f"{base_url}/primary_doc.xml")
            except httpx.HTTPError:
                xml_text = ""

        # 3. 如果仍然没有找到 infoTable，从目录列表中查找其他 XML 文件
        if not _has_info_table(xml_text):
            try:
                dir_resp = await _try_fetch_xml(c, f"{base_url}/")
                # 提取所有 .xml 链接（排除 primary_doc.xml）
                links = re.findall(r'href="([^"]+\.xml)"', dir_resp)
            except httpx.HTTPError:
                links = []

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
                try:
                    xml_text = await _try_fetch_xml(c, xml_url)
                    if _has_info_table(xml_text):
                        break
                except httpx.HTTPError:
                    continue

        if _has_info_table(xml_text):
            from etl.parser import parse_sec_13f_xml
            return parse_sec_13f_xml(xml_text)

        logger.warning(f"No holdings XML found for {accession_number}")
        return []
    except Exception as e:
        logger.error(f"SEC holdings fetch failed for {accession_number}: {e}")
        return []
    finally:
        if owns_client:
            await c.aclose()


async def fetch_fund_data(cik: str, quarters: int = 8) -> dict:
    """
    获取单个基金的所有数据（数据源：SEC EDGAR）

    返回: {
        "cik": str,
        "filings": list[dict],
        "holdings": dict[report_date, list[dict]],
        "source": "sec"
    }
    """
    async with httpx.AsyncClient(timeout=30) as client:
        filings = await fetch_filings_sec(cik, quarters, client=client)
        source = "sec"

        holdings_map = {}
        for filing in filings:
            acc = filing.get("accession_number")
            r_date = filing.get("report_date")
            if not acc or not r_date:
                continue
            h = await fetch_holdings_sec(cik, acc, client=client)
            if h:
                holdings_map[r_date] = h

        return {
            "cik": cik,
            "filings": filings,
            "holdings": holdings_map,
            "source": source,
        }
