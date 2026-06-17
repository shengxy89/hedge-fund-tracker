"""
测试数据抓取模块
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from etl.fetcher import fetch_filings_sec, RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter():
    limiter = RateLimiter(0.1)
    import asyncio
    t0 = asyncio.get_event_loop().time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_fetch_filings_sec_mock():
    """fetch_filings_sec 解析 SEC EDGAR submissions JSON,验证 13F-HR 过滤与排序"""
    mock_data = {
        "filings": {
            "recent": {
                "form": ["13F-HR", "10-K", "13F-HR/A"],
                "accessionNumber": ["0001-22-33", "0002-33-44", "0003-55-66"],
                "filingDate": ["2024-01-15", "2024-02-01", "2024-04-20"],
                "reportDate": ["2023-12-31", "2023-12-31", "2024-03-31"],
            }
        }
    }
    with patch("etl.fetcher._get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await fetch_filings_sec("1067983", quarters=3)
        # 2 个 13F-HR (一个原始 + 一个 amendment)
        assert len(result) == 2
        # 按 report_date 降序：2024-03-31 在前
        assert result[0]["report_date"] == "2024-03-31"
        # amendment 标记正确
        amendments = [f for f in result if f["is_amendment"]]
        assert len(amendments) == 1
