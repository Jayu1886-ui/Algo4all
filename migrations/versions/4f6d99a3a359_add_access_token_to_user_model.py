"""Add access_token to User model

Revision ID: 4f6d99a3a359
Revises: f833111af50f
Create Date: 2025-09-28 11:39:16.006229

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4f6d99a3a359'
down_revision = 'f833111af50f'
branch_labels = None
depends_on = None

def upgrade():
    # Create intraday_ltp table
    op.create_table(
        'intraday_ltp',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instrument', sa.String(length=50), nullable=False),
        sa.Column('ltp', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('intraday_ltp', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_intraday_ltp_timestamp'), ['timestamp'], unique=False)

    # Create market_data table
    op.create_table(
        'market_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instrument', sa.String(length=50), nullable=False),
        sa.Column('short_sma', sa.Float(), nullable=True),
        sa.Column('medium_sma', sa.Float(), nullable=True),
        sa.Column('long_sma', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('market_data', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_market_data_timestamp'), ['timestamp'], unique=False)

    # ✅ Just add the new access_token column
    op.add_column('users', sa.Column('access_token', sa.LargeBinary(), nullable=True))


 

def downgrade():
    # Revert users.access_token change
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('encrypted_access_token', postgresql.BYTEA(), nullable=True))
        batch_op.drop_column('access_token')

    # Drop market_data indexes and table
    with op.batch_alter_table('market_data', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_market_data_timestamp'))
    op.drop_table('market_data')

    # Drop intraday_ltp indexes and table
    with op.batch_alter_table('intraday_ltp', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_intraday_ltp_timestamp'))
    op.drop_table('intraday_ltp')
