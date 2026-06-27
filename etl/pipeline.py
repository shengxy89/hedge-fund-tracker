"""
ETL Pipeline 主流程编排
"""
import asyncio
import json
from datetime import date, datetime

from loguru import logger

from config.settings import get_settings
from db.engine import engine, get_session
from db.models import EtlRun, Filing, Fund, Holding, Security
from etl.amendment_handler import get_latest_filings_by_quarter
from etl.cusip_resolver import resolve_cusips_batch
from etl.fetcher import fetch_fund_data

settings = get_settings()


async def process_single_fund(
    fund_id: int, cik: str, name: str, quarters: int = 8,
    semaphore: asyncio.Semaphore = None,
) -> dict:
    """处理单个基金：抓取 -> 解析 -> 入库"""
    logger.info(f"Processing fund {name} (CIK: {cik})")

    try:
        data = await fetch_fund_data(cik, quarters)
        filings = get_latest_filings_by_quarter(data.get("filings", []), quarters)
        holdings_map = data.get("holdings", {})
        source = data.get("source", "unknown")

        if not filings:
            logger.warning(f"No filings found for {name}")
            return {"fund": name, "status": "no_filings", "filings": 0, "holdings": 0}

        # 1. 收集所有 unique CUSIP 并批量解析（在 DB 事务外）
        all_cusips = set()
        prefilled = {}  # cusip -> {"ticker", "name"}
        for filing in filings:
            acc = filing.get("accession_number", "")
            holdings = holdings_map.get(acc, [])
            for h in holdings:
                cusip = h.get("cusip", "")
                if not cusip:
                    continue
                all_cusips.add(cusip)
                # 保留 prefilled ticker/name（只要有就保留，避免 OpenFIGI 失败时 securities 表为空）
                if cusip not in prefilled and (h.get("ticker") or h.get("name")):
                    prefilled[cusip] = {"ticker": h.get("ticker"), "name": h.get("name")}

        # 批量解析 CUSIP
        cusip_info = await resolve_cusips_batch(list(all_cusips))
        # 补充 prefilled ticker/name
        for cusip, info in prefilled.items():
            if cusip in cusip_info:
                if info.get("ticker"):
                    cusip_info[cusip]["ticker"] = info["ticker"]
                if info.get("name"):
                    cusip_info[cusip]["name"] = info["name"]
            else:
                cusip_info[cusip] = {
                    "cusip": cusip,
                    "ticker": info.get("ticker"),
                    "name": info.get("name"),
                    "sector": None,
                    "industry": None,
                }

        # 2. 入库
        with get_session() as session:
            # 一次性批量查询已存在的 Filing accession_number，避免逐个 N+1 查询
            acc_numbers = [f.get("accession_number") for f in filings if f.get("accession_number")]
            existing_by_acc: dict[str, Filing] = {}
            if acc_numbers:
                existing_filings = (
                    session.query(Filing)
                    .filter(Filing.accession_number.in_(acc_numbers))
                    .all()
                )
                existing_by_acc = {f.accession_number: f for f in existing_filings}

            total_holdings = 0
            for filing in filings:
                acc = filing.get("accession_number")
                r_date_str = filing.get("report_date")
                f_date_str = filing.get("filing_date")
                form_type = filing.get("form_type", "13F-HR")
                is_amendment = filing.get("is_amendment", "/A" in form_type)

                if not r_date_str:
                    continue
                try:
                    report_date = date.fromisoformat(r_date_str)
                    filing_date = date.fromisoformat(f_date_str) if f_date_str else report_date
                except ValueError:
                    continue

                existing = existing_by_acc.get(acc)
                if not existing:
                    f = Filing(
                        fund_id=fund_id,
                        accession_number=acc,
                        filing_date=filing_date,
                        report_date=report_date,
                        form_type=form_type,
                        is_amendment=is_amendment,
                    )
                    session.add(f)
                    session.flush()

                # 获取该 accession_number 对应的 holdings
                holdings = holdings_map.get(acc, [])
                if not holdings:
                    logger.warning(f"No holdings data for {name} accession {acc}")
                    continue

                # 合并同一 CUSIP+putCall 的重复记录（累加 shares 和 value）
                merged = {}
                for h in holdings:
                    cusip = h.get("cusip", "")
                    if not cusip:
                        continue
                    key = (cusip, h.get("put_call") or "")
                    if key not in merged:
                        merged[key] = {
                            "cusip": cusip,
                            "name": h.get("name"),
                            "ticker": h.get("ticker"),
                            "shares": h.get("shares", 0),
                            "value": h.get("value", 0),
                            "put_call": h.get("put_call"),
                        }
                    else:
                        merged[key]["shares"] += h.get("shares", 0)
                        merged[key]["value"] += h.get("value", 0)
                holdings = list(merged.values())

                # 删除旧 holdings（amendment 覆盖）
                session.query(Holding).filter(
                    Holding.fund_id == fund_id,
                    Holding.report_date == report_date,
                ).delete(synchronize_session=False)

                # 计算 total_value
                total_value = sum(h.get("value", 0) for h in holdings)

                # 更新 filing 统计
                if existing:
                    existing.total_value = total_value
                    existing.holding_count = len(holdings)
                else:
                    f.total_value = total_value
                    f.holding_count = len(holdings)

                # 确保每个 CUSIP 在 securities 表中至少有一行记录（analytics join 前提）
                for h in holdings:
                    cusip = h.get("cusip", "")
                    if not cusip:
                        continue
                    sec = session.query(Security).filter(Security.cusip == cusip).first()
                    resolved = cusip_info.get(cusip, {})
                    ticker = h.get("ticker") or resolved.get("ticker")
                    sec_name = h.get("name") or resolved.get("name")
                    if sec:
                        if ticker and not sec.ticker:
                            sec.ticker = ticker
                        if sec_name and not sec.name:
                            sec.name = sec_name
                    else:
                        session.add(Security(
                            cusip=cusip,
                            ticker=ticker,
                            name=sec_name,
                            sector=resolved.get("sector"),
                            industry=resolved.get("industry"),
                        ))

                # 插入 holdings
                for h in holdings:
                    cusip = h.get("cusip", "")
                    if not cusip:
                        continue

                    resolved = cusip_info.get(cusip, {})
                    shares = h.get("shares", 0)
                    value = h.get("value", 0)
                    weight_pct = (value / total_value * 100) if total_value > 0 else 0

                    holding = Holding(
                        fund_id=fund_id,
                        report_date=report_date,
                        cusip=cusip,
                        ticker=h.get("ticker") or resolved.get("ticker"),
                        name=h.get("name") or resolved.get("name"),
                        shares=shares,
                        value=value,
                        weight_pct=round(weight_pct, 4),
                        put_call=h.get("put_call"),
                    )
                    session.add(holding)
                    total_holdings += 1

            logger.info(f"Fund {name}: {len(filings)} filings, {total_holdings} holdings inserted (source: {source})")
            return {
                "fund": name,
                "status": "success",
                "filings": len(filings),
                "holdings": total_holdings,
                "source": source,
            }

    except Exception as e:
        logger.error(f"Failed to process {name}: {e}")
        return {"fund": name, "status": "error", "error": str(e)}


def _log_etl_run(
    run_id: int | None,
    *,
    status: str,
    funds_total: int,
    funds_success: int,
    funds_failed: int,
    funds_no_filings: int,
    holdings_inserted: int,
    error_message: str | None = None,
    meta: dict | None = None,
) -> None:
    """写入/更新 etl_runs 记录。run_id 为 None 时插入新记录并返回 id。"""
    try:
        with get_session() as session:
            if run_id is None:
                run = EtlRun(
                    run_type="etl",
                    started_at=datetime.utcnow(),
                    status="running",
                    funds_total=funds_total,
                )
                session.add(run)
                session.flush()
                return run.id
            existing = session.get(EtlRun, run_id)
            if existing is None:
                return None
            existing.finished_at = datetime.utcnow()
            existing.status = status
            existing.funds_total = funds_total
            existing.funds_success = funds_success
            existing.funds_failed = funds_failed
            existing.funds_no_filings = funds_no_filings
            existing.holdings_inserted = holdings_inserted
            existing.error_message = error_message
            existing.meta = json.dumps(meta, ensure_ascii=False) if meta else None
            return existing.id
    except Exception as e:
        logger.warning(f"Failed to log ETL run: {e}")
        return None


async def run_etl_pipeline(fund_ciks: list[str] | None = None, quarters: int = 8) -> dict:
    """
    ETL Pipeline 主编排
    :param fund_ciks: 指定 CIK 列表，None 表示全部 active 基金
    :param quarters: 最近多少个季度
    :return: ETL 结果摘要
    """
    logger.info(f"Starting ETL pipeline for quarters={quarters}")

    with get_session(read_only=True) as session:
        query = session.query(Fund.fund_id, Fund.cik, Fund.name).filter(Fund.is_active.is_(True))
        if fund_ciks:
            query = query.filter(Fund.cik.in_(fund_ciks))
        fund_rows = query.all()

    logger.info(f"Found {len(fund_rows)} funds to process")

    run_id = _log_etl_run(
        None, status="running",
        funds_total=len(fund_rows), funds_success=0,
        funds_failed=0, funds_no_filings=0, holdings_inserted=0,
    )

    try:
        # SQLite 不支持并发写入，顺序执行；PostgreSQL 可并发
        db_type = engine.url.get_dialect().name
        results = []
        if db_type == "sqlite":
            for fid, cik, name in fund_rows:
                r = await process_single_fund(fid, cik, name, quarters)
                results.append(r)
        else:
            semaphore = asyncio.Semaphore(5)
            tasks = [process_single_fund(fid, cik, name, quarters, semaphore) for fid, cik, name in fund_rows]
            results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        _log_etl_run(
            run_id, status="failed",
            funds_total=len(fund_rows), funds_success=0,
            funds_failed=len(fund_rows), funds_no_filings=0,
            holdings_inserted=0, error_message=str(e),
            meta={"quarters": quarters},
        )
        raise

    summary = {
        "total": len(fund_rows),
        "success": 0,
        "failed": 0,
        "no_filings": 0,
        "holdings_inserted": 0,
        "details": [],
    }
    for r in results:
        if isinstance(r, Exception):
            summary["failed"] += 1
            summary["details"].append({"status": "error", "error": str(r)})
        else:
            summary["details"].append(r)
            summary["holdings_inserted"] += r.get("holdings", 0)
            if r["status"] == "success":
                summary["success"] += 1
            elif r["status"] == "no_filings":
                summary["no_filings"] += 1
            else:
                summary["failed"] += 1

    if summary["failed"] == 0 and summary["success"] > 0:
        final_status = "success"
    elif summary["success"] > 0:
        final_status = "partial"
    else:
        final_status = "failed"

    _log_etl_run(
        run_id, status=final_status,
        funds_total=summary["total"],
        funds_success=summary["success"],
        funds_failed=summary["failed"],
        funds_no_filings=summary["no_filings"],
        holdings_inserted=summary["holdings_inserted"],
        meta={"quarters": quarters, "source": "sec"},
    )

    logger.info(
        f"ETL complete: {summary['success']} success, {summary['failed']} failed, "
        f"{summary['no_filings']} no filings"
    )
    return summary
