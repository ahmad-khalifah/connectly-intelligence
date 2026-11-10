"""Community records: settlements, facilities, claims; observation bounds, identity and defaults.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10 17:14:54.878885
"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('claim',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subject_type', sa.Enum('admin_area', 'settlement', name='claim_subject', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('attribute', sa.String(length=64), nullable=False),
    sa.Column('value_text', sa.Text(), nullable=False),
    sa.Column('value_type', sa.Enum('measured', 'estimated', 'modelled', 'derived', 'assumed', 'ai_generated', name='claim_value_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('source_description', sa.Text(), nullable=False),
    sa.Column('source_url', sa.String(length=1024), nullable=True),
    sa.Column('observed_on', sa.String(length=32), nullable=True),
    sa.Column('verification_status', sa.Enum('unverified', 'source_verified', 'field_verified', 'disputed', 'retired', name='claim_verification', native_enum=False, create_constraint=True, length=32), server_default='unverified', nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('verified_by_id', sa.Integer(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_claim'))
    )
    op.create_index('ix_claim_subject', 'claim', ['subject_type', 'subject_id', 'attribute'], unique=False)
    op.create_geospatial_table('facility',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('health', 'education', 'financial', 'telecom', 'energy', 'market', 'transport', 'agriculture', 'community', 'other', name='facility_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('subtype', sa.String(length=128), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('source_code', sa.String(length=128), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('geom', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('operational_status', sa.String(length=64), nullable=True),
    sa.Column('ownership', sa.String(length=64), nullable=True),
    sa.Column('verification_status', sa.Enum('unverified', 'source_verified', 'field_verified', 'disputed', 'retired', name='facility_verification', native_enum=False, create_constraint=True, length=32), server_default='unverified', nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ward_id', sa.Integer(), nullable=True),
    sa.Column('lga_id', sa.Integer(), nullable=True),
    sa.Column('state_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset.id'], name=op.f('fk_facility_dataset_id_dataset'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lga_id'], ['admin_area.id'], name=op.f('fk_facility_lga_id_admin_area'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['state_id'], ['admin_area.id'], name=op.f('fk_facility_state_id_admin_area'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ward_id'], ['admin_area.id'], name=op.f('fk_facility_ward_id_admin_area'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_facility')),
    sa.UniqueConstraint('dataset_id', 'source_code', name='uq_facility_dataset_code')
    )
    op.create_geospatial_index('idx_facility_geom', 'facility', ['geom'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_facility_dataset_id'), 'facility', ['dataset_id'], unique=False)
    op.create_index('ix_facility_kind', 'facility', ['kind', 'subtype'], unique=False)
    op.create_index(op.f('ix_facility_lga_id'), 'facility', ['lga_id'], unique=False)
    op.create_index(op.f('ix_facility_state_id'), 'facility', ['state_id'], unique=False)
    op.create_index(op.f('ix_facility_ward_id'), 'facility', ['ward_id'], unique=False)
    op.create_geospatial_table('settlement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('source_name', sa.String(length=255), nullable=True),
    sa.Column('source_code', sa.String(length=128), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=True),
    sa.Column('settlement_type', sa.String(length=64), nullable=True),
    sa.Column('point', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('extent', Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('verification_status', sa.Enum('unverified', 'source_verified', 'field_verified', 'disputed', 'retired', name='settlement_verification', native_enum=False, create_constraint=True, length=32), server_default='unverified', nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ward_id', sa.Integer(), nullable=True),
    sa.Column('lga_id', sa.Integer(), nullable=True),
    sa.Column('state_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset.id'], name=op.f('fk_settlement_dataset_id_dataset'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lga_id'], ['admin_area.id'], name=op.f('fk_settlement_lga_id_admin_area'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['state_id'], ['admin_area.id'], name=op.f('fk_settlement_state_id_admin_area'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ward_id'], ['admin_area.id'], name=op.f('fk_settlement_ward_id_admin_area'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement')),
    sa.UniqueConstraint('dataset_id', 'source_code', name='uq_settlement_dataset_code')
    )
    op.create_geospatial_index('idx_settlement_extent', 'settlement', ['extent'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_geospatial_index('idx_settlement_point', 'settlement', ['point'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_settlement_dataset_id'), 'settlement', ['dataset_id'], unique=False)
    op.create_index(op.f('ix_settlement_lga_id'), 'settlement', ['lga_id'], unique=False)
    op.create_index('ix_settlement_name', 'settlement', ['name'], unique=False)
    op.create_index(op.f('ix_settlement_state_id'), 'settlement', ['state_id'], unique=False)
    op.create_index(op.f('ix_settlement_ward_id'), 'settlement', ['ward_id'], unique=False)
    op.add_column('observation', sa.Column('lower_bound', sa.Float(), nullable=True))
    op.add_column('observation', sa.Column('upper_bound', sa.Float(), nullable=True))
    op.add_column('observation', sa.Column('interval_note', sa.String(length=128), nullable=True))
    op.add_column('observation', sa.Column('note', sa.Text(), nullable=True))
    op.alter_column('observation', 'verification_status', server_default='unverified')
    op.create_unique_constraint('uq_observation_identity', 'observation', ['indicator_id', 'geo_level', 'geo_id', 'period', 'dataset_id'])


def downgrade() -> None:
    op.drop_constraint('uq_observation_identity', 'observation', type_='unique')
    op.alter_column('observation', 'verification_status', server_default=None)
    op.drop_column('observation', 'note')
    op.drop_column('observation', 'interval_note')
    op.drop_column('observation', 'upper_bound')
    op.drop_column('observation', 'lower_bound')
    op.drop_index(op.f('ix_settlement_ward_id'), table_name='settlement')
    op.drop_index(op.f('ix_settlement_state_id'), table_name='settlement')
    op.drop_index('ix_settlement_name', table_name='settlement')
    op.drop_index(op.f('ix_settlement_lga_id'), table_name='settlement')
    op.drop_index(op.f('ix_settlement_dataset_id'), table_name='settlement')
    op.drop_geospatial_index('idx_settlement_point', table_name='settlement', postgresql_using='gist', column_name='point')
    op.drop_geospatial_index('idx_settlement_extent', table_name='settlement', postgresql_using='gist', column_name='extent')
    op.drop_geospatial_table('settlement')
    op.drop_index(op.f('ix_facility_ward_id'), table_name='facility')
    op.drop_index(op.f('ix_facility_state_id'), table_name='facility')
    op.drop_index(op.f('ix_facility_lga_id'), table_name='facility')
    op.drop_index('ix_facility_kind', table_name='facility')
    op.drop_index(op.f('ix_facility_dataset_id'), table_name='facility')
    op.drop_geospatial_index('idx_facility_geom', table_name='facility', postgresql_using='gist', column_name='geom')
    op.drop_geospatial_table('facility')
    op.drop_index('ix_claim_subject', table_name='claim')
    op.drop_table('claim')
