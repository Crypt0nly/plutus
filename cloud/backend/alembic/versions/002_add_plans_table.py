"""Add plans table for cloud agent plan manager.

Revision ID: 002
Revises: 001
Create Date: 2026-03-21

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_user_id"), "plans", ["user_id"], unique=False)
    op.create_index(op.f("ix_plans_status"), "plans", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_plans_status"), table_name="plans")
    op.drop_index(op.f("ix_plans_user_id"), table_name="plans")
    op.drop_table("plans")
