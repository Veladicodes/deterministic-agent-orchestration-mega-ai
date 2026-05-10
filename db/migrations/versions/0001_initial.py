"""initial migration

Revision ID: 0001_initial
Revises: 
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Initial empty migration - schema will be created by later revisions.
    pass


def downgrade() -> None:
    pass
