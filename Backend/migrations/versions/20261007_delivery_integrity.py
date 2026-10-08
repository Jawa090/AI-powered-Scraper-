"""Search columns, immutable delivery snapshots and completion outbox.

Revision ID: 20261007_delivery
Revises: 9f8b7c6a5d4e
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261007_delivery"
down_revision = "9f8b7c6a5d4e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leads", sa.Column("record_kind", sa.String(30), nullable=False, server_default="company"))
    for name, typ in [("category", sa.String(255)), ("city", sa.String(100)), ("us_state", sa.String(2)), ("source_url", sa.Text()), ("content_hash", sa.String(64))]:
        op.add_column("leads", sa.Column(name, typ))
    op.add_column("leads", sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"))
    op.execute("""UPDATE leads SET record_kind = CASE WHEN lower(source_code) IN ('bonfire','dasny','nyscr','ny') THEN 'opportunity' ELSE 'company' END,
        category = NULLIF(lead_metadata->>'category',''), city = NULLIF(lead_metadata->>'city',''),
        us_state = CASE WHEN length(COALESCE(lead_metadata->>'us_state', lead_metadata->>'state'))=2
            THEN upper(COALESCE(lead_metadata->>'us_state', lead_metadata->>'state')) END,
        source_url = COALESCE(lead_metadata->>'source_url', lead_metadata->>'url')""")
    op.execute("""UPDATE leads SET source_id=s.id FROM sources s
        WHERE lower(s.code)=lower(leads.source_code) AND leads.source_id IS NULL""")
    for col in ["record_kind", "category", "city", "us_state"]:
        op.create_index(f"ix_leads_{col}", "leads", [col])
    op.create_index("ix_leads_search_location", "leads", ["us_state", "city", "record_kind"])
    op.add_column("queries", sa.Column("response", JSONB()))
    op.add_column("query_results", sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("query_results", sa.Column("snapshot", JSONB()))
    op.create_index("ix_query_results_delivery_version", "query_results", ["lead_id", "record_version"])
    op.create_table("session_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("session_id", sa.String(100), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("query_id", sa.String(100), sa.ForeignKey("queries.id"), nullable=False),
        sa.Column("job_id", sa.String(100), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("reply", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "query_id", name="uq_session_events_job_query"))
    for col in ["session_id", "query_id", "job_id", "status"]:
        op.create_index(f"ix_session_events_{col}", "session_events", [col])
    # Preserve every legacy conversation while selecting a single active one.
    op.execute("""WITH ranked AS (SELECT id, row_number() OVER(PARTITION BY user_id ORDER BY created_at DESC, id DESC) AS n
        FROM agent_sessions WHERE status='active' AND user_id IS NOT NULL)
        UPDATE agent_sessions SET status='archived' WHERE id IN (SELECT id FROM ranked WHERE n>1)""")
    op.create_index("uq_sessions_active_user", "agent_sessions", ["user_id"], unique=True,
                    postgresql_where=sa.text("status='active' AND user_id IS NOT NULL"))


def downgrade():
    op.drop_index("uq_sessions_active_user", "agent_sessions")
    op.drop_table("session_events")
    op.drop_index("ix_query_results_delivery_version", "query_results")
    op.drop_column("query_results", "snapshot")
    op.drop_column("query_results", "record_version")
    op.drop_column("queries", "response")
    op.drop_index("ix_leads_search_location", "leads")
    for col in ["record_kind", "category", "city", "us_state"]:
        op.drop_index(f"ix_leads_{col}", "leads")
    for col in ["record_kind", "category", "city", "us_state", "source_url", "content_hash", "content_version"]:
        op.drop_column("leads", col)
