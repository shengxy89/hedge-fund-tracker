"""
SQLAlchemy ORM Models for 13F Hedge Fund Tracker
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Fund(Base):
    """基金主表"""
    __tablename__ = "funds"

    fund_id = Column(Integer, primary_key=True, autoincrement=True)
    cik = Column(String(20), unique=True, nullable=False, comment="SEC CIK 编号")
    name = Column(String(255), nullable=False, comment="基金公司名称")
    manager = Column(String(255), comment="基金经理")
    strategy = Column(String(100), comment="投资策略分类: Growth/Value/Event-Driven/Multi-Strategy 等")
    is_active = Column(Boolean, default=True, comment="是否仍在追踪")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    filings = relationship("Filing", back_populates="fund")
    holdings = relationship("Holding", back_populates="fund")


class Filing(Base):
    """13F Filing 记录表"""
    __tablename__ = "filings"

    filing_id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    accession_number = Column(String(50), unique=True, nullable=False, comment="SEC Accession Number")
    filing_date = Column(Date, nullable=False, comment="SEC 收到日期")
    report_date = Column(Date, nullable=False, comment="持仓报告日期（季末）")
    form_type = Column(String(20), nullable=False, comment="13F-HR / 13F-HR/A")
    is_amendment = Column(Boolean, default=False, comment="是否为修正版")
    total_value = Column(BigInteger, comment="该期总市值（千美元）")
    holding_count = Column(Integer, comment="持仓股票数量")
    created_at = Column(DateTime, default=func.now())

    fund = relationship("Fund", back_populates="filings")

    __table_args__ = (
        Index("ix_filings_fund_report", "fund_id", "report_date"),
    )


class Security(Base):
    """证券主数据表"""
    __tablename__ = "securities"

    cusip = Column(String(9), primary_key=True, comment="CUSIP 编号")
    ticker = Column(String(20), comment="股票代码")
    name = Column(String(255), comment="公司名称")
    sector = Column(String(100), comment="GICS Sector")
    industry = Column(String(100), comment="GICS Industry")
    market_cap = Column(BigInteger, comment="最近市值")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Holding(Base):
    """持仓明细表（核心表）"""
    __tablename__ = "holdings"

    holding_id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    report_date = Column(Date, nullable=False, comment="季末日期")
    cusip = Column(String(9), ForeignKey("securities.cusip"), nullable=False)
    ticker = Column(String(20), comment="冗余 ticker，加速查询")
    name = Column(String(255), comment="冗余公司名")
    shares = Column(BigInteger, nullable=False, comment="持股数量")
    value = Column(BigInteger, nullable=False, comment="市值（千美元）")
    weight_pct = Column(Float, comment="占该基金总持仓比重 %")
    put_call = Column(String(10), comment="PUT / CALL / None")

    fund = relationship("Fund", back_populates="holdings")
    security = relationship("Security")

    __table_args__ = (
        UniqueConstraint("fund_id", "report_date", "cusip", "put_call", name="uq_holding"),
        Index("ix_holdings_ticker", "ticker"),
        Index("ix_holdings_report_date", "report_date"),
    )


class HoldingDelta(Base):
    """季度调仓变化表"""
    __tablename__ = "holding_deltas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    cusip = Column(String(9), ForeignKey("securities.cusip"), nullable=False)
    ticker = Column(String(20))
    put_call = Column(String(10), comment="PUT / CALL / None")
    quarter = Column(String(7), nullable=False, comment="格式: 2024Q3")
    prev_quarter = Column(String(7), comment="上一季度: 2024Q2")
    action = Column(String(10), nullable=False, comment="NEW / SOLD / ADD / REDUCE")
    shares_prev = Column(BigInteger, default=0)
    shares_curr = Column(BigInteger, default=0)
    shares_change = Column(BigInteger, nullable=False, comment="变化量")
    shares_change_pct = Column(Float, comment="变化百分比")
    value_prev = Column(BigInteger, default=0)
    value_curr = Column(BigInteger, default=0)
    value_change = Column(BigInteger, nullable=False)
    weight_prev = Column(Float, default=0)
    weight_curr = Column(Float, default=0)
    weight_change_pct = Column(Float, comment="权重变化 = weight_curr - weight_prev")

    __table_args__ = (
        UniqueConstraint("fund_id", "cusip", "put_call", "quarter", name="uq_delta"),
        Index("ix_deltas_quarter", "quarter"),
        Index("ix_deltas_action", "action"),
    )


class HoldingDeltaNorm(Base):
    """多基金调仓共识信号标准化表"""
    __tablename__ = "holding_delta_norms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quarter = Column(String(7), nullable=False, comment="格式: 2024Q3")
    cusip = Column(String(9), ForeignKey("securities.cusip"), nullable=False)
    put_call = Column(String(10), comment="PUT / CALL / None")
    consensus_action = Column(String(10), nullable=False, comment="NEW / SOLD / ADD / REDUCE")
    fund_count = Column(Integer, nullable=False, comment="参与基金数")
    avg_weight_change_pct = Column(Float, nullable=False, comment="平均权重变化 %")
    total_weight_change_pct = Column(Float, comment="总权重变化 %")
    signal_score = Column(Float, nullable=False, comment="信号强度 = fund_count * abs(avg_weight_change_pct)")
    fund_size_tier = Column(String(10), comment="mega / large / medium / small")
    action_norm_score = Column(Float, comment="标准化动作强度")
    conviction_score = Column(Float, comment="综合置信度")
    holder_count = Column(Integer, default=0, comment="当前季度持有该标的的基金数")
    crowding_score = Column(Float, default=0, comment="拥挤度 = holder_count / 总基金数")

    __table_args__ = (
        UniqueConstraint("quarter", "cusip", "put_call", "consensus_action", name="uq_delta_norm"),
        Index("ix_delta_norm_quarter", "quarter"),
        Index("ix_delta_norm_action", "consensus_action"),
    )


class FundOverlap(Base):
    """基金间趋同度表"""
    __tablename__ = "fund_overlaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_a_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    fund_b_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    quarter = Column(String(7), nullable=False, comment="格式: 2024Q3")
    jaccard_score = Column(Float, nullable=False, comment="Jaccard 相似度 0~1")
    overlap_count = Column(Integer, nullable=False, comment="重叠股票数量")
    overlap_tickers = Column(Text, comment="重叠 ticker 列表, 逗号分隔")

    __table_args__ = (
        UniqueConstraint("fund_a_id", "fund_b_id", "quarter", name="uq_overlap"),
        Index("ix_overlap_quarter", "quarter"),
    )


class SectorWeight(Base):
    """板块权重表"""
    __tablename__ = "sector_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey("funds.fund_id"), nullable=False)
    quarter = Column(String(7), nullable=False, comment="格式: 2024Q3")
    sector = Column(String(100), nullable=False, comment="GICS Sector 名称")
    weight_pct = Column(Float, nullable=False, comment="板块权重占比 %")
    holding_count = Column(Integer, comment="该板块持仓数量")
    total_value = Column(BigInteger, comment="该板块总市值（千美元）")

    __table_args__ = (
        UniqueConstraint("fund_id", "quarter", "sector", name="uq_sector_weight"),
    )


class EtlRun(Base):
    """ETL 运行日志表 — 记录每次 ETL/分析运行的状态、统计、错误"""
    __tablename__ = "etl_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String(30), nullable=False, comment="etl | analytics | full_pipeline")
    started_at = Column(DateTime, nullable=False, default=func.now())
    finished_at = Column(DateTime, comment="完成时间（NULL 表示运行中）")
    status = Column(String(20), nullable=False, comment="success | partial | failed | running")
    funds_total = Column(Integer, default=0, comment="目标基金数")
    funds_success = Column(Integer, default=0)
    funds_failed = Column(Integer, default=0)
    funds_no_filings = Column(Integer, default=0)
    holdings_inserted = Column(Integer, default=0)
    error_message = Column(Text, comment="失败时的错误摘要")
    meta = Column(Text, comment="JSON 序列化的额外元信息")
