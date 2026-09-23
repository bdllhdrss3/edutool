"""Add document language, per-document quiz history, and account recovery codes."""
import sqlalchemy as sa
from alembic import op

revision = "0003_language_quiz_recovery"
down_revision = "0002_document_hash"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    if "recovery_code_hash" not in user_columns:
        op.add_column("users", sa.Column("recovery_code_hash", sa.String(64), nullable=True))
    if "language" not in document_columns:
        op.add_column("documents", sa.Column("language", sa.String(2), nullable=False, server_default="en"))
    if "quiz_question_history" not in inspector.get_table_names():
        op.create_table(
            "quiz_question_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("normalized_question", sa.String(1000), nullable=False),
            sa.Column("source_page", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_quiz_question_history_document_id", "quiz_question_history", ["document_id"])
        op.create_index("ix_quiz_question_history_normalized_question", "quiz_question_history", ["normalized_question"])


def downgrade():
    raise RuntimeError("Language and quiz-history downgrade is disabled; restore a verified backup instead")