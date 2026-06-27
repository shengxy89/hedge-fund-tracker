"""add concentration analytics schema

Revision ID: c0a4f1d2e3b5
Revises: 349de66ae8f1
Create Date: 2026-06-27 00:00:00.000000

为本地分析算法扩展 schema：
- holding_deltas 加 value_change_pct（weight_change_pct 已由 456edea1a8de 添加）
- holding_delta_norms 加 6 个金额/权重维度列（供 consensus 聚合）
- fund_overlaps 加加权 Jaccard 与市值占比 3 列
- 新建 fund_concentrations 表（单基金集中度 HHI / top-N 权重）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c0a4f1d2e3b5'
down_revision: str | Sequence[str] | None = '349de66ae8f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add concentration analytics columns and fund_concentrations table."""

    # 1) holding_deltas: value_change_pct（weight_change_pct 已在 456edea1a8de 添加）
    op.add_column(
        'holding_deltas',
        sa.Column('value_change_pct', sa.Float(), nullable=True,
                  comment='市值变化百分比，value_change / value_prev * 100'),
    )

    # 2) holding_delta_norms: 6 个金额/权重维度列（consensus 聚合消费）
    op.add_column(
        'holding_delta_norms',
        sa.Column('total_value_change', sa.BigInteger(), nullable=True,
                  comment='共识方向下总市值变化，千美元'),
    )
    op.add_column(
        'holding_delta_norms',
        sa.Column('avg_value_change', sa.Float(), nullable=True,
                  comment='平均市值变化，千美元'),
    )
    op.add_column(
        'holding_delta_norms',
        sa.Column('total_abs_value_change', sa.BigInteger(), nullable=True,
                  comment='绝对市值变化合计，千美元'),
    )
    op.add_column(
        'holding_delta_norms',
        sa.Column('avg_value_change_pct', sa.Float(), nullable=True,
                  comment='平均市值变化百分比'),
    )
    op.add_column(
        'holding_delta_norms',
        sa.Column('avg_weight_curr', sa.Float(), nullable=True,
                  comment='当前平均权重'),
    )
    op.add_column(
        'holding_delta_norms',
        sa.Column('total_weight_curr', sa.Float(), nullable=True,
                  comment='当前权重合计'),
    )

    # 3) fund_overlaps: 加权 Jaccard 与重合市值占比
    op.add_column(
        'fund_overlaps',
        sa.Column('weighted_jaccard_score', sa.Float(), nullable=True,
                  comment='按持仓权重计算的加权 Jaccard'),
    )
    op.add_column(
        'fund_overlaps',
        sa.Column('overlap_value_pct_a', sa.Float(), nullable=True,
                  comment='重合持仓占基金A 13F市值百分比'),
    )
    op.add_column(
        'fund_overlaps',
        sa.Column('overlap_value_pct_b', sa.Float(), nullable=True,
                  comment='重合持仓占基金B 13F市值百分比'),
    )

    # 4) fund_concentrations 表（单基金集中度指标）
    op.create_table(
        'fund_concentrations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fund_id', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.String(length=7), nullable=False, comment='格式: 2024Q3'),
        sa.Column('top_1_weight', sa.Float(), nullable=True, comment='第一大持仓权重 %'),
        sa.Column('top_5_weight', sa.Float(), nullable=True, comment='前五大持仓权重 %'),
        sa.Column('top_10_weight', sa.Float(), nullable=True, comment='前十大持仓权重 %'),
        sa.Column('hhi', sa.Float(), nullable=True, comment='赫芬达尔-赫希曼指数'),
        sa.Column('holding_count', sa.Integer(), nullable=True, comment='持仓股票数量'),
        sa.Column('total_value', sa.BigInteger(), nullable=True, comment='该期总市值（千美元）'),
        sa.ForeignKeyConstraint(['fund_id'], ['funds.fund_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fund_id', 'quarter', name='uq_fund_concentration'),
    )
    op.create_index('ix_concentration_quarter', 'fund_concentrations', ['quarter'])


def downgrade() -> None:
    op.drop_index('ix_concentration_quarter', table_name='fund_concentrations')
    op.drop_table('fund_concentrations')

    op.drop_column('fund_overlaps', 'overlap_value_pct_b')
    op.drop_column('fund_overlaps', 'overlap_value_pct_a')
    op.drop_column('fund_overlaps', 'weighted_jaccard_score')

    op.drop_column('holding_delta_norms', 'total_weight_curr')
    op.drop_column('holding_delta_norms', 'avg_weight_curr')
    op.drop_column('holding_delta_norms', 'avg_value_change_pct')
    op.drop_column('holding_delta_norms', 'total_abs_value_change')
    op.drop_column('holding_delta_norms', 'avg_value_change')
    op.drop_column('holding_delta_norms', 'total_value_change')

    op.drop_column('holding_deltas', 'value_change_pct')
