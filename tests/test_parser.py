"""
测试 SEC XML 解析
"""
from etl.parser import parse_sec_13f_xml

SAMPLE_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>AAPL</titleOfClass>
    <cusip>037833100</cusip>
    <value>100000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>1000000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parse_sec_13f_xml():
    """测试 XML 能正确解析出一条 holding，value 保持千美元单位"""
    holdings = parse_sec_13f_xml(SAMPLE_XML)
    assert len(holdings) == 1, f"Expected 1 holding, got {len(holdings)}"
    assert holdings[0]["cusip"] == "037833100"
    assert holdings[0]["name"] == "APPLE INC"
    assert holdings[0]["shares"] == 1000000
    assert holdings[0]["value"] == 100000  # SEC XML value 保持千美元，不乘 1000
    assert holdings[0]["ticker"] is None  # parser 不解析 ticker，由 CUSIP resolver 处理


def test_parse_empty_xml():
    holdings = parse_sec_13f_xml("<root></root>")
    assert holdings == []


def test_parse_amendment_holdings_match():
    """测试 amendment 对应的 holdings 能通过 accession_number 正确匹配"""
    # 构造模拟数据：同一 report_date 有两个 filing，原始版和 amendment
    filings = [
        {
            "accession_number": "ORIG001",
            "report_date": "2024-03-31",
            "filing_date": "2024-05-01",
            "form_type": "13F-HR",
            "is_amendment": False,
        },
        {
            "accession_number": "AMEND001",
            "report_date": "2024-03-31",
            "filing_date": "2024-05-15",
            "form_type": "13F-HR/A",
            "is_amendment": True,
        },
    ]

    # holdings_map 以 accession_number 为 key
    holdings_map = {
        "ORIG001": [
            {"cusip": "111", "name": "OLD", "shares": 100, "value": 1000},
        ],
        "AMEND001": [
            {"cusip": "222", "name": "NEW", "shares": 200, "value": 2000},
        ],
    }

    # amendment_handler 会选择 filing_date 最新的 amendment
    from etl.amendment_handler import get_latest_filings_by_quarter
    latest = get_latest_filings_by_quarter(filings, quarters=8)
    assert len(latest) == 1
    chosen = latest[0]
    assert chosen["accession_number"] == "AMEND001"

    # pipeline 应该用 accession_number 取 holdings
    holdings = holdings_map.get(chosen["accession_number"], [])
    assert len(holdings) == 1
    assert holdings[0]["cusip"] == "222"
