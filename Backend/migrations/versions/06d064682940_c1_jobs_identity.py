"""c1_jobs_identity

Revision ID: 06d064682940
Revises: 77c60b18519c
Create Date: 2026-10-05 22:24:53.393638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06d064682940'
down_revision: Union[str, None] = '77c60b18519c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to jobs
    op.add_column('jobs', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('worker_id', sa.String(length=100), nullable=True))
    op.add_column('jobs', sa.Column('waiting_for', sa.String(length=50), nullable=True))
    op.add_column('jobs', sa.Column('resume_requested', sa.Boolean(), server_default='false', nullable=False))
    op.create_unique_constraint('uq_jobs_idempotency_key', 'jobs', ['idempotency_key'])

    # 2. Add columns to leads and index on due_at
    op.add_column('leads', sa.Column('identity_key', sa.String(length=300), nullable=True))
    op.add_column('leads', sa.Column('due_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_leads_due_at', 'leads', ['due_at'], unique=False)

    # 3. Add column to organizations
    op.add_column('organizations', sa.Column('dedup_key', sa.String(length=64), nullable=True))

    # 4. Add columns to queries
    op.add_column('queries', sa.Column('client_message_id', sa.String(length=100), nullable=True))
    op.add_column('queries', sa.Column('turn_id', sa.String(length=100), nullable=True))

    # 5. Add index on agent_messages(session_id, created_at)
    op.create_index('ix_agent_messages_session_created_at', 'agent_messages', ['session_id', 'created_at'], unique=False)

    # 6. Make nullable specified columns
    op.alter_column('emails', 'email_type', existing_type=sa.VARCHAR(length=50), nullable=True)
    op.alter_column('phones', 'phone_type', existing_type=sa.VARCHAR(length=50), nullable=True)
    op.alter_column('locations', 'country', existing_type=sa.VARCHAR(length=50), nullable=True, server_default=None)
    op.alter_column('requirements', 'quantity', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('jobs', 'total_target', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('sources', 'version', existing_type=sa.VARCHAR(length=50), nullable=True)
    op.alter_column('sources', 'default_limit', existing_type=sa.INTEGER(), nullable=True)

    # 7. Lowercase source codes
    op.execute("UPDATE sources SET code = lower(code)")
    op.execute("UPDATE leads SET source_code = lower(source_code) WHERE source_code IS NOT NULL")
    op.execute("UPDATE lead_sources SET source_code = lower(source_code) WHERE source_code IS NOT NULL")
    op.execute("UPDATE jobs SET script_id = lower(script_id) WHERE script_id IS NOT NULL")


def downgrade() -> None:
    # 7. (Lowercased codes are compatible with legacy uppercase, no inverse needed)

    # 6. Restore NOT NULL constraints on specified columns
    op.execute("UPDATE emails SET email_type = 'work' WHERE email_type IS NULL")
    op.alter_column('emails', 'email_type', existing_type=sa.VARCHAR(length=50), nullable=False)

    op.execute("UPDATE phones SET phone_type = 'office' WHERE phone_type IS NULL")
    op.alter_column('phones', 'phone_type', existing_type=sa.VARCHAR(length=50), nullable=False)

    op.execute("UPDATE locations SET country = 'USA' WHERE country IS NULL")
    op.alter_column('locations', 'country', existing_type=sa.VARCHAR(length=50), nullable=False)

    op.execute("UPDATE requirements SET quantity = 20 WHERE quantity IS NULL")
    op.alter_column('requirements', 'quantity', existing_type=sa.INTEGER(), nullable=False)

    op.execute("UPDATE jobs SET total_target = 20 WHERE total_target IS NULL")
    op.alter_column('jobs', 'total_target', existing_type=sa.INTEGER(), nullable=False)

    op.execute("UPDATE sources SET version = '1.0.0' WHERE version IS NULL")
    op.alter_column('sources', 'version', existing_type=sa.VARCHAR(length=50), nullable=False)

    op.execute("UPDATE sources SET default_limit = 20 WHERE default_limit IS NULL")
    op.alter_column('sources', 'default_limit', existing_type=sa.INTEGER(), nullable=False)

    # 5. Drop index on agent_messages
    op.drop_index('ix_agent_messages_session_created_at', table_name='agent_messages')

    # 4. Drop columns from queries
    op.drop_column('queries', 'turn_id')
    op.drop_column('queries', 'client_message_id')

    # 3. Drop column from organizations
    op.drop_column('organizations', 'dedup_key')

    # 2. Drop index and columns from leads
    op.drop_index('ix_leads_due_at', table_name='leads')
    op.drop_column('leads', 'due_at')
    op.drop_column('leads', 'identity_key')

    # 1. Drop columns from jobs
    op.drop_column('jobs', 'resume_requested')
    op.drop_column('jobs', 'waiting_for')
    op.drop_column('jobs', 'worker_id')
    op.drop_column('jobs', 'error_message')
