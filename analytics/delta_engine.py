"""
季度调仓计算引擎
使用 Polars DataFrame 进行高性能计算
"""
from datetime import date, datetime

import polars as pl
from loguru import logger
from sqlalchemy import text

from db.engine import engine
from utils import date_to_quarter


def get_holdings_df(fund_id: int, report_date) -> pl.DataFrame:
    """从数据库读取某基金某季度的持仓为 Polars DataFrame"""
    query = """
    SELECT
        h.cusip,
        h.ticker,
        h.name,
        h.shares,
        h.value,
        h.weight_pct,
        h.put_call,
        COALESCE(s.sector, 'Unknown') as sector
    FROM holdings h
    LEFT JOIN securities s ON h.cusip = s.cusip
    WHERE h.fund_id = :fund_id AND h.report_date = :report_date
    """
    date_str = report_date.isoformat() if hasattr(report_date, 'isoformat') else str(report_date)
    with engine.connect() as conn:
        df = pl.read_database(
            query, conn,
            execute_options={"parameters": {"fund_id": fund_id, "report_date": date_str}},
            schema_overrides={
                "cusip": pl.String,
                "ticker": pl.String,
                "name": pl.String,
                "shares": pl.Int64,
                "value": pl.Float64,
                "weight_pct": pl.Float64,
                "put_call": pl.String,
                "sector": pl.String,
            }
        )
    return df


def get_fund_quarters(fund_id: int) -> list[str]:
    """获取某基金有数据的所有季度，按升序排列"""
    query = """
    SELECT DISTINCT report_date
    FROM holdings
    WHERE fund_id = :fund_id
    ORDER BY report_date ASC
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {"fund_id": fund_id})
        dates = [row[0] for row in result.fetchall()]
        # Convert string dates to date objects if needed
        parsed_dates = []
        for d in dates:
            if isinstance(d, str):
                d = datetime.strptime(d, "%Y-%m-%d").date()
            parsed_dates.append(d)
        dates = parsed_dates
    return [date_to_quarter(d) for d in dates]


def compute_deltas_from_frames(
    curr: pl.DataFrame, prev: pl.DataFrame, fund_id: int, curr_date: date, prev_date: date
) -> pl.DataFrame:
    """
    纯函数：计算单个基金从 prev_date 到 curr_date 的调仓变化
    返回 HoldingDelta 格式的 DataFrame
    """
    if curr.is_empty() and prev.is_empty():
        return pl.DataFrame()

    # Polars join 不匹配 null，需先填充
    curr = curr.with_columns(pl.col("put_call").fill_null("NONE"))
    prev = prev.with_columns(pl.col("put_call").fill_null("NONE"))

    # 外连接（按 cusip + put_call）
    joined = curr.join(
        prev,
        on=["cusip", "put_call"],
        how="full",
        suffix="_prev"
    )

    # 修复：full join 当左表无匹配时 key 列为 null，需用 coalesce 合并
    joined = joined.with_columns([
        pl.coalesce(pl.col("cusip"), pl.col("cusip_prev")).alias("cusip"),
        pl.coalesce(pl.col("put_call"), pl.col("put_call_prev")).alias("put_call"),
    ])

    # 填充 null
    joined = joined.fill_null(0)

    quarter = date_to_quarter(curr_date)
    prev_quarter = date_to_quarter(prev_date)

    # 判断 action
    joined = joined.with_columns([
        pl.when(pl.col("shares_prev") == 0)
        .then(pl.lit("NEW"))
        .when(pl.col("shares") == 0)
        .then(pl.lit("SOLD"))
        .when(pl.col("shares") > pl.col("shares_prev"))
        .then(pl.lit("ADD"))
        .when(pl.col("shares") < pl.col("shares_prev"))
        .then(pl.lit("REDUCE"))
        .otherwise(pl.lit("HOLD"))
        .alias("action"),

        (pl.col("shares") - pl.col("shares_prev")).alias("shares_change"),
        (pl.col("value") - pl.col("value_prev")).alias("value_change"),
    ])

    # 计算变化百分比
    joined = joined.with_columns([
        pl.when(pl.col("shares_prev") > 0)
        .then(pl.col("shares_change") / pl.col("shares_prev") * 100)
        .otherwise(
            pl.when(pl.col("action") == "NEW")
            .then(pl.lit(100.0))
            .when(pl.col("action") == "SOLD")
            .then(pl.lit(-100.0))
            .otherwise(None)
        )
        .alias("shares_change_pct"),
        (pl.col("weight_pct") - pl.col("weight_pct_prev")).alias("weight_change_pct"),
        pl.when(pl.col("value_prev") > 0)
        .then(pl.col("value_change") / pl.col("value_prev") * 100)
        .otherwise(
            pl.when(pl.col("action") == "NEW").then(pl.lit(100.0))
            .when(pl.col("action") == "SOLD").then(pl.lit(-100.0))
            .otherwise(None)
        )
        .alias("value_change_pct"),
    ])

    # 过滤掉 HOLD 和 cusip 为空的
    joined = joined.filter(
        (pl.col("action") != "HOLD") &
        (pl.col("cusip").is_not_null()) &
        (pl.col("cusip") != "")
    )

    # 选择输出列
    result = joined.select([
        pl.lit(fund_id).alias("fund_id"),
        pl.col("cusip"),
        pl.col("ticker").alias("ticker"),
        pl.col("put_call"),
        pl.lit(quarter).alias("quarter"),
        pl.lit(prev_quarter).alias("prev_quarter"),
        pl.col("action"),
        pl.col("shares_prev"),
        pl.col("shares").alias("shares_curr"),
        pl.col("shares_change"),
        pl.col("shares_change_pct"),
        pl.col("value_prev"),
        pl.col("value").alias("value_curr"),
        pl.col("value_change"),
        pl.col("value_change_pct"),
        pl.col("weight_pct_prev").alias("weight_prev"),
        pl.col("weight_pct").alias("weight_curr"),
        pl.col("weight_change_pct"),
    ])

    return result


def compute_deltas_for_fund(fund_id: int, curr_date: date, prev_date: date) -> pl.DataFrame:
    """
    计算单个基金从 prev_date 到 curr_date 的调仓变化
    返回 HoldingDelta 格式的 DataFrame
    """
    curr = get_holdings_df(fund_id, curr_date)
    prev = get_holdings_df(fund_id, prev_date)
    return compute_deltas_from_frames(curr, prev, fund_id, curr_date, prev_date)


def run_delta_engine(fund_ids: list[int] | None = None):
    """
    运行调仓计算引擎
    :param fund_ids: 指定基金列表，None 表示全部
    """
    from db.engine import get_session
    from db.models import Fund

    with get_session(read_only=True) as session:
        if fund_ids is None:
            funds = session.query(Fund).all()
        else:
            funds = session.query(Fund).filter(Fund.fund_id.in_(fund_ids)).all()
        fund_info = [(f.fund_id, f.name) for f in funds]

    logger.info(f"Running delta engine for {len(fund_info)} funds...")

    all_deltas = []
    for fund_id, fund_name in fund_info:
        # 获取该基金所有有数据的 report_date
        query = """
        SELECT DISTINCT report_date FROM holdings WHERE fund_id = :fund_id ORDER BY report_date ASC
        """
        with engine.connect() as conn:
            result = conn.execute(text(query), {"fund_id": fund_id})
            dates = [row[0] for row in result.fetchall()]
            parsed_dates = []
            for d in dates:
                if isinstance(d, str):
                    d = datetime.strptime(d, "%Y-%m-%d").date()
                parsed_dates.append(d)
            dates = parsed_dates

        if len(dates) < 2:
            logger.debug(f"Fund {fund_name} has only {len(dates)} quarters, skipping delta")
            continue

        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]
            df = compute_deltas_for_fund(fund_id, curr_date, prev_date)
            if not df.is_empty():
                all_deltas.append(df)

    if not all_deltas:
        logger.info("No deltas to compute.")
        return 0

    combined = pl.concat(all_deltas)

    # 写入数据库（仅删除本次涉及的季度，避免全表清空）
    quarters_touched = sorted({q for q in combined["quarter"].to_list() if q})
    with engine.connect() as conn:
        if quarters_touched:
            placeholders = ",".join(f":q{i}" for i in range(len(quarters_touched)))
            params = {f"q{i}": q for i, q in enumerate(quarters_touched)}
            conn.execute(text(f"DELETE FROM holding_deltas WHERE quarter IN ({placeholders})"), params)
        conn.commit()

    # 使用 pandas 作为中间格式写入（SQLAlchemy 兼容性更好）
    pd_df = combined.to_pandas()
    pd_df.to_sql("holding_deltas", engine, if_exists="append", index=False)

    logger.info(f"[OK] Delta engine complete. {len(pd_df)} delta records computed.")
    return len(pd_df)
