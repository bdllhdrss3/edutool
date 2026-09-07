"""Baseline: create a fresh schema or inspect and adopt the legacy schema in place."""
import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def baseline_metadata():
    # Frozen independently from live ORM models so future model changes cannot alter history.
    metadata = sa.MetaData()
    sa.Table("users", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("documents", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("document_pages", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id"), nullable=False, index=True),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False))
    sa.Table("conversations", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id")),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    sa.Table("messages", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    return metadata


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    metadata = baseline_metadata()
    present = set(inspector.get_table_names()) & set(metadata.tables)
    if not present:
        metadata.create_all(connection)
        return
    if present != set(metadata.tables):
        raise RuntimeError("Incomplete legacy schema; back up and review it before migration")
    for name, table in metadata.tables.items():
        columns = {column["name"] for column in inspector.get_columns(name)}
        if not set(table.columns.keys()) <= columns:
            raise RuntimeError(f"Legacy table {name} is missing required baseline columns")
    # Existing data, including already-added hashes/indexes, is deliberately untouched.


def downgrade():
    raise RuntimeError("Destructive baseline downgrade is disabled; restore a verified backup instead")