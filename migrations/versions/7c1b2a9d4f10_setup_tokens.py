"""Add setup tokens for deep-link settings.

Revision ID: 7c1b2a9d4f10
Revises: f2b1c8d4a9e7
Create Date: 2026-01-24
"""

from alembic import op
import sqlalchemy as sa


def _table_exists(conn, name: str) -> bool:
    inspector = sa.inspect(conn)
    return name in inspector.get_table_names()


def _index_exists(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(idx["name"] == name for idx in inspector.get_indexes(table))


# revision identifiers, used by Alembic.
revision = "7c1b2a9d4f10"
down_revision = "f2b1c8d4a9e7"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not _table_exists(conn, "setup_tokens"):
        op.create_table(
            "setup_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token", sa.Text(), nullable=False),
            sa.Column("chat_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("used_at", sa.Text(), nullable=True),
            sa.Column("used_by", sa.Integer(), nullable=True),
            sa.UniqueConstraint("token", name="uq_setup_token"),
        )
    if _table_exists(conn, "setup_tokens") and not _index_exists(conn, "setup_tokens", "idx_setup_tokens_chat_id"):
        op.create_index("idx_setup_tokens_chat_id", "setup_tokens", ["chat_id"])


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "setup_tokens") and _index_exists(conn, "setup_tokens", "idx_setup_tokens_chat_id"):
        op.drop_index("idx_setup_tokens_chat_id", table_name="setup_tokens")
    if _table_exists(conn, "setup_tokens"):
        op.drop_table("setup_tokens")
