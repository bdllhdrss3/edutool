"""Add nullable content hashes and per-user uniqueness, or adopt the additive schema."""
import sqlalchemy as sa
from alembic import op

revision = "0002_document_hash"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("documents")}
    indexes = {index["name"]: index for index in inspector.get_indexes("documents")}
    name = "ix_documents_user_file_hash"
    if name in indexes:
        index = indexes[name]
        if not index["unique"] or index["column_names"] != ["user_id", "file_hash"]:
            raise RuntimeError("Existing hash index has an incompatible definition; review before migration")
    if "file_hash" not in columns:
        op.add_column("documents", sa.Column("file_hash", sa.String(64), nullable=True))
    else:
        duplicates = connection.execute(sa.text(
            "SELECT user_id FROM documents WHERE file_hash IS NOT NULL "
            "GROUP BY user_id, file_hash HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicates:
            raise RuntimeError("Duplicate non-null hashes exist; migration will not modify user data automatically")
    if name not in indexes:
        op.create_index(name, "documents", ["user_id", "file_hash"], unique=True)


def downgrade():
    raise RuntimeError("Hash-removing downgrade is disabled; restore a verified backup instead")