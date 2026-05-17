"""
SEC 13F XML 解析器
"""
import xml.etree.ElementTree as ET
from loguru import logger


def parse_sec_13f_xml(xml_text: str) -> list[dict]:
    """
    解析 SEC 13F INFO TABLE XML
    返回标准化持仓列表
    """
    holdings = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        return holdings

    # 处理命名空间
    ns = {"ns": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}

    # 尝试有命名空间和无命名空间两种路径
    info_tables = root.findall(".//ns:infoTable", ns) or root.findall(".//infoTable")

    for table in info_tables:
        def get_text(tag: str) -> str:
            el = table.find(f"ns:{tag}", ns)
            if el is None:
                el = table.find(tag)
            return (el.text or "").strip() if el is not None else ""

        cusip = get_text("cusip")
        if not cusip:
            continue

        name = get_text("nameOfIssuer")
        # titleOfClass 不是 ticker（通常是 "COM", "CL A" 等）
        # 真正的 ticker 需要通过 CUSIP 解析（OpenFIGI）获得
        ticker = None

        # shares 可能在 shrsOrPrnAmt/sshPrnamt 子结构中
        shares_str = get_text("sshPrnamt")
        if not shares_str.isdigit():
            shares_el = table.find(".//ns:sshPrnamt", ns)
            if shares_el is None:
                shares_el = table.find(".//sshPrnamt")
            shares_str = (shares_el.text or "0").strip() if shares_el is not None else "0"

        value_str = get_text("value")
        put_call = get_text("putCall")

        try:
            shares = int(shares_str)
        except ValueError:
            shares = 0
        try:
            value = int(value_str)  # 13F 中 value 已经是千美元单位
        except ValueError:
            value = 0

        holdings.append({
            "cusip": cusip,
            "name": name,
            "ticker": ticker,
            "shares": shares,
            "value": value,
            "put_call": put_call.upper() if put_call else None,
        })

    return holdings
