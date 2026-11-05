"""Add unified business settings.

Revision ID: 20261105_0001
Revises: 20261101_0001
"""
from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261105_0001'
down_revision = '20261101_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Startup may already have added this table to an existing installation.
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table('application_settings'):
        return
    op.create_table('application_settings',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('namespace', sa.String(64), nullable=False),
        sa.Column('key', sa.String(128), nullable=False),
        sa.Column('value', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('namespace', 'key', name='uq_application_settings_namespace_key'),
    )


def downgrade():
    op.drop_table('application_settings')
