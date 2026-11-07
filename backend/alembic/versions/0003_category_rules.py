"""category rules learned from manual categorisation

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07 20:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('category_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=300), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('category_rules')
