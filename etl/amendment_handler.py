"""
Amendment 去重处理模块
"""
from datetime import datetime
from collections import defaultdict
from loguru import logger


def deduplicate_filings(filings: list[dict]) -> list[dict]:
    """
    对同一基金同一 report_date 的多个 filing 进行去重：
    - 如果存在 13F-HR/A，只保留 filing_date 最新的 amendment
    - 如果只有 13F-HR，直接使用
    """
    # 按 report_date 分组
    by_report_date = defaultdict(list)
    for f in filings:
        rd = f.get("report_date")
        if rd:
            by_report_date[rd].append(f)

    result = []
    for rd, group in by_report_date.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        # 分离 amendment 和原始版
        amendments = [f for f in group if f.get("is_amendment") or "/A" in f.get("form_type", "")]
        originals = [f for f in group if f not in amendments]

        if amendments:
            # 保留 filing_date 最新的 amendment
            amendments.sort(key=lambda x: x.get("filing_date", ""), reverse=True)
            chosen = amendments[0]
            logger.info(f"Report date {rd}: using amendment {chosen['accession_number']} over {len(originals)} original(s)")
        elif originals:
            chosen = originals[0]
        else:
            continue
        result.append(chosen)

    # 按 report_date 降序
    result.sort(key=lambda x: x.get("report_date", ""), reverse=True)
    return result


def get_latest_filings_by_quarter(filings: list[dict], quarters: int = 8) -> list[dict]:
    """
    获取最近 quarters 个季度的有效 filings（已处理 amendment）
    """
    deduped = deduplicate_filings(filings)
    return deduped[:quarters]
