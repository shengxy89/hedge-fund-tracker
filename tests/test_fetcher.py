"""
测试数据抓取模块
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from etl.fetcher import fetch_filings_forms13f, RateLimiter


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
async def test_fetch_filings_forms13f_mock():
    mock_data = [
        {"accession_number": "ACC1", "filing_date": "2024-01-01", "report_date": "2023-12-31", "form_type": "13F-HR"},
        {"accession_number": "ACC2", "filing_date": "2024-04-01", "report_date": "2024-03-31", "form_type": "13F-HR"},
    ]
    with patch("etl.fetcher._get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"filings": mock_data}
        result = await fetch_filings_forms13f("1067983", quarters=2)
        assert len(result) == 2
        assert result[0]["form_type"] == "13F-HR"
