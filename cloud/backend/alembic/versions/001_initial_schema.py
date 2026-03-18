"""initial schema

Revision ID: 001
Revises: -
Create Date: 2025-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === users (root table — no foreign keys) ===
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("plan", sa.String(), nullable=True, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("settings", sa.JSON(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column(
            "connector_credentials",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # === agent_states ===
    op.create_table(
        "agent_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True, server_default="idle"),
        sa.Column("current_task", sa.Text(), nullable=True),
        sa.Column("execution_context", sa.String(), nullable=True, server_default="cloud"),
        sa.Column("bridge_connected", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_agent_states_user_id"),
    )
    op.create_index(op.f("ix_agent_states_user_id"), "agent_states", ["user_id"])

    # === memories ===
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("sync_version", sa.Integer(), nullable=True, server_default=sa.text("1")),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memories_user_id"),
    )
    op.create_index(op.f("ix_memories_user_id"), "memories", ["user_id"])
    op.create_index(op.f("ix_memories_category"), "memories", ["category"])

    # === skills ===
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skill_type", sa.String(), nullable=True, server_default="simple"),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("sync_version", sa.Integer(), nullable=True, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_skills_user_id"),
    )
    op.create_index(op.f("ix_skills_user_id"), "skills", ["user_id"])

    # === scheduled_tasks ===
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schedule", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_scheduled_tasks_user_id"),
    )
    op.create_index(op.f("ix_scheduled_tasks_user_id"), "scheduled_tasks", ["user_id"])

    # === conversations ===
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_conversations_user_id"),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"])

    # === messages (depends on conversations AND users) ===
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_messages_user_id"),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"])
    op.create_index(op.f("ix_messages_user_id"), "messages", ["user_id"])

    # === sync_log ===
    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=True, server_default="cloud"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sync_log_user_id"),
    )
    op.create_index(op.f("ix_sync_log_user_id"), "sync_log", ["user_id"])


def downgrade() -> None:
    # Drop in reverse dependency order — leaf tables first, root table last.
    op.drop_index(op.f("ix_sync_log_user_id"), table_name="sync_log")
    op.drop_table("sync_log")

    op.drop_index(op.f("ix_messages_user_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")

    op.drop_index(op.f("ix_scheduled_tasks_user_id"), table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")

    op.drop_index(op.f("ix_skills_user_id"), table_name="skills")
    op.drop_table("skills")

    op.drop_index(op.f("ix_memories_category"), table_name="memories")
    op.drop_index(op.f("ix_memories_user_id"), table_name="memories")
    op.drop_table("memories")

    op.drop_index(op.f("ix_agent_states_user_id"), table_name="agent_states")
    op.drop_table("agent_states")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
