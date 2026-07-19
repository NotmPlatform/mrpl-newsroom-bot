"""Initial newsroom schema.

Revision ID: 0001_initial
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("author_role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("voice_file_id", sa.String(length=255), nullable=True),
        sa.Column("voice_duration", sa.Integer(), nullable=False),
        sa.Column("telegram_photos", sa.JSON(), nullable=False),
        sa.Column("media_group_ids", sa.JSON(), nullable=False),
        sa.Column("ai_payload", sa.JSON(), nullable=False),
        sa.Column("wp_media_ids", sa.JSON(), nullable=False),
        sa.Column("wp_post_id", sa.BigInteger(), nullable=True),
        sa.Column("wp_edit_url", sa.Text(), nullable=False),
        sa.Column("wp_preview_url", sa.Text(), nullable=False),
        sa.Column("wp_public_url", sa.Text(), nullable=False),
        sa.Column("rejection_comment", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submissions_author_id", "submissions", ["author_id"], unique=False)
    op.create_index(
        "ix_submissions_author_status",
        "submissions",
        ["author_id", "status"],
        unique=False,
    )
    op.create_index("ix_submissions_status", "submissions", ["status"], unique=False)
    op.create_index("ix_submissions_wp_post_id", "submissions", ["wp_post_id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("submission_id", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"], unique=False)
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"], unique=False)
    op.create_index(
        "ix_audit_events_submission_id",
        "audit_events",
        ["submission_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_submission_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_submissions_wp_post_id", table_name="submissions")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_author_status", table_name="submissions")
    op.drop_index("ix_submissions_author_id", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
