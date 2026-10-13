"""c2_unique_indexes

Revision ID: 9f8b7c6a5d4e
Revises: 06d064682940
Create Date: 2026-10-06 14:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f8b7c6a5d4e'
down_revision: Union[str, None] = '06d064682940'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure no null identity/dedup keys exist before creating unique indexes and NOT NULL
    op.execute("UPDATE leads SET identity_key = md5(id::text) WHERE identity_key IS NULL OR identity_key = ''")
    op.execute("UPDATE organizations SET dedup_key = md5(id::text) WHERE dedup_key IS NULL OR dedup_key = ''")

    # 1. uq_leads_identity_key
    op.create_index(
        'uq_leads_identity_key',
        'leads',
        ['identity_key'],
        unique=True,
    )
    op.alter_column('leads', 'identity_key', existing_type=sa.String(length=300), nullable=False)

    # 2. uq_org_dedup_key
    op.create_index(
        'uq_org_dedup_key',
        'organizations',
        ['dedup_key'],
        unique=True,
    )
    op.alter_column('organizations', 'dedup_key', existing_type=sa.String(length=64), nullable=False)

    # 3. uq_emails_owner
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_emails_owner
        ON emails (normalized_email, COALESCE(organization_id, ''), COALESCE(contact_id, ''))
    """)

    # 4. uq_phones_owner
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_phones_owner
        ON phones (normalized_phone, COALESCE(organization_id, ''), COALESCE(contact_id, ''))
    """)

    # 5. uq_contacts_org_name
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_org_name
        ON contacts (COALESCE(organization_id, ''), normalized_full_name)
    """)

    # 6. uq_locations_org_city_state
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_org_city_state
        ON locations (organization_id, COALESCE(city, ''), COALESCE(state, ''))
    """)

    # 7. uq_jobs_idempotency
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_idempotency
        ON jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # 8. uq_jobs_active_params
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_params
        ON jobs (script_id, params_hash)
        WHERE status IN ('Queued', 'Running', 'WaitingForUser')
    """)

    # 9. uq_queries_session_client_msg
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_queries_session_client_msg
        ON queries (session_id, client_message_id)
        WHERE client_message_id IS NOT NULL
    """)


def downgrade() -> None:
    # Drop partial and functional indexes
    op.execute("DROP INDEX IF EXISTS uq_queries_session_client_msg")
    op.execute("DROP INDEX IF EXISTS uq_jobs_active_params")
    op.execute("DROP INDEX IF EXISTS uq_jobs_idempotency")
    op.execute("DROP INDEX IF EXISTS uq_locations_org_city_state")
    op.execute("DROP INDEX IF EXISTS uq_contacts_org_name")
    op.execute("DROP INDEX IF EXISTS uq_phones_owner")
    op.execute("DROP INDEX IF EXISTS uq_emails_owner")

    # Revert NOT NULL on organizations.dedup_key and drop index
    op.alter_column('organizations', 'dedup_key', existing_type=sa.String(length=64), nullable=True)
    op.drop_index('uq_org_dedup_key', table_name='organizations')

    # Revert NOT NULL on leads.identity_key and drop index
    op.alter_column('leads', 'identity_key', existing_type=sa.String(length=300), nullable=True)
    op.drop_index('uq_leads_identity_key', table_name='leads')
