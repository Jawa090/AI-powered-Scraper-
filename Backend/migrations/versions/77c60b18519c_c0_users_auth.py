"""c0_users_auth

Revision ID: 77c60b18519c
Revises: b226615a3c81
Create Date: 2026-10-05 20:23:06.494289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77c60b18519c'
down_revision: Union[str, None] = 'b226615a3c81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 2. Add columns, initially nullable
    op.add_column('users', sa.Column('username', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('auth_source', sa.String(length=10), nullable=True))

    # 3. Make email and model nullable
    op.alter_column('agents', 'model',
               existing_type=sa.VARCHAR(length=100),
               nullable=True)
    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)

    # 1. Insert department and agent
    op.execute("INSERT INTO departments (id, name, code) VALUES ('dept-default', 'Default', 'DEFAULT') ON CONFLICT (id) DO NOTHING")
    op.execute("INSERT INTO agents (id, department_id, name, code, status, capabilities, created_at) VALUES ('agent-master', 'dept-default', 'DataOps Agent', 'agent-master', 'idle', '[]'::jsonb, NOW()) ON CONFLICT (id) DO NOTHING")

    # 4. Migrate existing users
    op.execute("UPDATE users SET role='user', status='Disabled', auth_source='db', username=id")

    # 5. Make auth_source NOT NULL
    op.alter_column('users', 'auth_source', existing_type=sa.VARCHAR(length=10), nullable=False)

    # 6. & 7. Create unique indexes
    op.execute("CREATE UNIQUE INDEX uq_users_username_lower ON users (lower(username)) WHERE username IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_users_single_admin ON users ((role)) WHERE role = 'admin'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_single_admin")
    op.execute("DROP INDEX IF EXISTS uq_users_username_lower")

    op.alter_column('users', 'email',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.drop_column('users', 'auth_source')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'username')
    op.alter_column('agents', 'model',
               existing_type=sa.VARCHAR(length=100),
               nullable=False)
