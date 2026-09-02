"""programmes become a library; assignments carry (client, day)

Revision ID: 73ce539f9248
Revises: 21e17bf1e446
Create Date: 2026-09-02 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73ce539f9248'
down_revision: Union[str, Sequence[str], None] = '21e17bf1e446'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Split content from ownership.

    Until now a programme was welded to one client (programs.user_id). Now the
    programme is a reusable library item and `program_assignments` says who gets
    it on which day. Every existing bound programme is BACKFILLED as one
    assignment (dated by its last edit), so nothing already handed out is lost.
    """
    op.create_table(
        "program_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("program_id", "user_id", "date",
                            name="uq_assignment_program_user_date"),
    )
    op.create_index("ix_program_assignments_program_id", "program_assignments", ["program_id"])
    op.create_index("ix_program_assignments_user_id", "program_assignments", ["user_id"])
    op.create_index("ix_program_assignments_date", "program_assignments", ["date"])

    op.execute("""
        INSERT INTO program_assignments (program_id, user_id, date)
        SELECT id, user_id, COALESCE(updated_at::date, CURRENT_DATE)
        FROM programs
        WHERE user_id IS NOT NULL
    """)

    # dropping the column drops its FK and index with it (PostgreSQL)
    op.drop_column("programs", "user_id")


def downgrade() -> None:
    """Best-effort: re-bind each programme to its FIRST assignee."""
    op.add_column("programs", sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE programs p SET user_id = (
            SELECT a.user_id FROM program_assignments a
            WHERE a.program_id = p.id ORDER BY a.date, a.id LIMIT 1
        )
    """)
    op.create_foreign_key("programs_user_id_fkey", "programs", "users",
                          ["user_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_programs_user_id", "programs", ["user_id"])
    op.drop_index("ix_program_assignments_date", table_name="program_assignments")
    op.drop_index("ix_program_assignments_user_id", table_name="program_assignments")
    op.drop_index("ix_program_assignments_program_id", table_name="program_assignments")
    op.drop_table("program_assignments")
