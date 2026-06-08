"""hiring leads: ease score and contact provenance links

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('business_contacts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('opportunity_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('contact_purpose', sa.String(length=40), nullable=False, server_default=''))
        batch_op.create_index(batch_op.f('ix_business_contacts_opportunity_id'), ['opportunity_id'], unique=False)
        batch_op.create_foreign_key('fk_business_contacts_opportunity', 'opportunities', ['opportunity_id'], ['id'])

    with op.batch_alter_table('opportunities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ease_score', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ease_signals', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('apply_method', sa.String(length=10), nullable=False, server_default='unknown'))


def downgrade() -> None:
    with op.batch_alter_table('opportunities', schema=None) as batch_op:
        batch_op.drop_column('apply_method')
        batch_op.drop_column('ease_signals')
        batch_op.drop_column('ease_score')

    with op.batch_alter_table('business_contacts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_business_contacts_opportunity', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_business_contacts_opportunity_id'))
        batch_op.drop_column('contact_purpose')
        batch_op.drop_column('opportunity_id')
