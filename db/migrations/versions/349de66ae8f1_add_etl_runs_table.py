"""add etl_runs table

Revision ID: 349de66ae8f1
Revises: 456edea1a8de
Create Date: 2026-06-17 21:12:59.093411

只创建 etl_runs 表；SQLite 不支持 ALTER COLUMN SET NOT NULL 等操作，
其他 autogenerate 噪声 op 已手工删除。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '349de66ae8f1'
down_revision: str | Sequence[str] | None = '456edea1a8de'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create etl_runs table for ETL run logging."""
    op.create_table(
        'etl_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_type', sa.String(length=30), nullable=False,
                  comment='etl | analytics | full_pipeline'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True,
                  comment='完成时间（NULL 表示运行中）'),
        sa.Column('status', sa.String(length=20), nullable=False,
                  comment='success | partial | failed | running'),
        sa.Column('funds_total', sa.Integer(), nullable=True, comment='目标基金数'),
        sa.Column('funds_success', sa.Integer(), nullable=True),
        sa.Column('funds_failed', sa.Integer(), nullable=True),
        sa.Column('funds_no_filings', sa.Integer(), nullable=True),
        sa.Column('holdings_inserted', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True, comment='失败时的错误摘要'),
        sa.Column('meta', sa.Text(), nullable=True, comment='JSON 序列化的额外元信息'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('etl_runs')
