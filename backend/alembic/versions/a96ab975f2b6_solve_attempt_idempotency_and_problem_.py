"""solve attempt idempotency and problem uniqueness

Revision ID: a96ab975f2b6
Revises: 4594cf56bba2
Create Date: 2026-08-10 03:49:00.889419
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a96ab975f2b6'
down_revision: Union[str, None] = '4594cf56bba2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode: SQLite can't ALTER constraints in place (it does a table
    # copy-and-move under the hood); Postgres runs these as plain ALTER TABLEs.
    with op.batch_alter_table('problem') as batch_op:
        batch_op.create_unique_constraint('uq_problem_platform_ppid', ['platform', 'platform_problem_id'])
    with op.batch_alter_table('solveattempt') as batch_op:
        batch_op.add_column(sa.Column('client_event_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.create_index(op.f('ix_solveattempt_client_event_id'), ['client_event_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('solveattempt') as batch_op:
        batch_op.drop_index(op.f('ix_solveattempt_client_event_id'))
        batch_op.drop_column('client_event_id')
    with op.batch_alter_table('problem') as batch_op:
        batch_op.drop_constraint('uq_problem_platform_ppid', type_='unique')
