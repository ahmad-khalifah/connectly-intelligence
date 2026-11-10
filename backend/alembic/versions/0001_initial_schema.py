"""Initial schema: provenance, administrative hierarchy, sectors, indicators,
observations and data gaps.

Revision ID: 0001
Revises: 
Create Date: 2026-11-10 11:08:42.919152
"""
from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostGIS must exist before any geometry column. No-op if already installed.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table('sector',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_priority', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sector')),
    sa.UniqueConstraint('code', name=op.f('uq_sector_code'))
    )
    op.create_table('source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('url', sa.String(length=1024), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source')),
    sa.UniqueConstraint('key', name=op.f('uq_source_key'))
    )
    op.create_table('data_gap',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('geographic_scope', sa.String(length=255), nullable=False),
    sa.Column('status', sa.Enum('open', 'partially_addressed', 'resolved', name='data_gap_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('candidate_sources', sa.Text(), nullable=True),
    sa.Column('needs_field_verification', sa.Boolean(), nullable=False),
    sa.Column('identified_on', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sector_id'], ['sector.id'], name=op.f('fk_data_gap_sector_id_sector')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_gap')),
    sa.UniqueConstraint('code', name=op.f('uq_data_gap_code'))
    )
    op.create_index(op.f('ix_data_gap_sector_id'), 'data_gap', ['sector_id'], unique=False)
    op.create_table('dataset',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('distributor', sa.String(length=255), nullable=True),
    sa.Column('title', sa.String(length=512), nullable=False),
    sa.Column('version', sa.String(length=128), nullable=True),
    sa.Column('publication_date', sa.Date(), nullable=True),
    sa.Column('source_update_text', sa.String(length=255), nullable=True),
    sa.Column('reference_period', sa.String(length=128), nullable=True),
    sa.Column('geographic_coverage', sa.String(length=512), nullable=True),
    sa.Column('method_summary', sa.Text(), nullable=True),
    sa.Column('limitations', sa.Text(), nullable=True),
    sa.Column('licence', sa.String(length=255), nullable=True),
    sa.Column('licence_url', sa.String(length=1024), nullable=True),
    sa.Column('licence_verified', sa.Boolean(), nullable=False),
    sa.Column('commercial_use_allowed', sa.Boolean(), nullable=True),
    sa.Column('landing_url', sa.String(length=1024), nullable=True),
    sa.Column('download_url', sa.String(length=1024), nullable=True),
    sa.Column('file_name', sa.String(length=512), nullable=True),
    sa.Column('file_sha256', sa.String(length=64), nullable=True),
    sa.Column('file_bytes', sa.BigInteger(), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('record_count', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('registered', 'loaded', 'failed', 'superseded', name='dataset_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('fk_dataset_source_id_source')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset')),
    sa.UniqueConstraint('key', name=op.f('uq_dataset_key'))
    )
    op.create_table('indicator',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=True),
    sa.Column('unit', sa.String(length=64), nullable=False),
    sa.Column('higher_is_worse', sa.Boolean(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('method', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sector_id'], ['sector.id'], name=op.f('fk_indicator_sector_id_sector')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_indicator')),
    sa.UniqueConstraint('code', name=op.f('uq_indicator_code'))
    )
    op.create_index(op.f('ix_indicator_sector_id'), 'indicator', ['sector_id'], unique=False)
    op.create_table('need_category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['sector_id'], ['sector.id'], name=op.f('fk_need_category_sector_id_sector')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_need_category')),
    sa.UniqueConstraint('code', name=op.f('uq_need_category_code'))
    )
    op.create_index(op.f('ix_need_category_sector_id'), 'need_category', ['sector_id'], unique=False)
    op.create_geospatial_table('admin_area',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('level', sa.Enum('country', 'state', 'lga', 'ward', name='admin_level', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_name', sa.String(length=255), nullable=False),
    sa.Column('source_code', sa.String(length=128), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('parent_method', sa.Enum('spatial_overlap', 'none', name='parent_method', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('parent_overlap', sa.Float(), nullable=True),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('area_km2', sa.Float(), nullable=True),
    sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset.id'], name=op.f('fk_admin_area_dataset_id_dataset'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['admin_area.id'], name=op.f('fk_admin_area_parent_id_admin_area'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_area')),
    sa.UniqueConstraint('dataset_id', 'level', 'source_code', name='uq_admin_area_dataset_code')
    )
    op.create_geospatial_index('idx_admin_area_geom', 'admin_area', ['geom'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_admin_area_dataset_id'), 'admin_area', ['dataset_id'], unique=False)
    op.create_index('ix_admin_area_level_active', 'admin_area', ['level', 'active'], unique=False)
    op.create_index('ix_admin_area_name', 'admin_area', ['name'], unique=False)
    op.create_index(op.f('ix_admin_area_parent_id'), 'admin_area', ['parent_id'], unique=False)
    op.create_table('ingest_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('running', 'succeeded', 'failed', 'skipped', name='ingest_run_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('rows_read', sa.Integer(), nullable=True),
    sa.Column('rows_loaded', sa.Integer(), nullable=True),
    sa.Column('rows_rejected', sa.Integer(), nullable=True),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset.id'], name=op.f('fk_ingest_run_dataset_id_dataset'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingest_run'))
    )
    op.create_table('observation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('indicator_id', sa.Integer(), nullable=False),
    sa.Column('geo_level', sa.Enum('country', 'state', 'lga', 'ward', 'settlement', name='observation_geo_level', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('geo_id', sa.Integer(), nullable=False),
    sa.Column('period', sa.String(length=32), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('value_text', sa.Text(), nullable=True),
    sa.Column('margin_of_error', sa.Float(), nullable=True),
    sa.Column('value_type', sa.Enum('measured', 'estimated', 'modelled', 'derived', 'assumed', 'ai_generated', name='value_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('verification_status', sa.Enum('unverified', 'source_verified', 'field_verified', 'disputed', 'retired', name='verification_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('source_reference', sa.String(length=512), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('value IS NOT NULL OR value_text IS NOT NULL', name=op.f('ck_observation_has_value')),
    sa.ForeignKeyConstraint(['dataset_id'], ['dataset.id'], name=op.f('fk_observation_dataset_id_dataset'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['indicator_id'], ['indicator.id'], name=op.f('fk_observation_indicator_id_indicator')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_observation'))
    )
    op.create_index(op.f('ix_observation_dataset_id'), 'observation', ['dataset_id'], unique=False)
    op.create_index('ix_observation_lookup', 'observation', ['indicator_id', 'geo_level', 'geo_id', 'period'], unique=False)
    op.create_table('place_alias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_area_id', sa.Integer(), nullable=False),
    sa.Column('alias', sa.String(length=255), nullable=False),
    sa.Column('source', sa.String(length=255), nullable=True),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['admin_area_id'], ['admin_area.id'], name=op.f('fk_place_alias_admin_area_id_admin_area'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_place_alias')),
    sa.UniqueConstraint('admin_area_id', 'alias', name='uq_place_alias_area_alias')
    )
    op.create_index(op.f('ix_place_alias_admin_area_id'), 'place_alias', ['admin_area_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_place_alias_admin_area_id'), table_name='place_alias')
    op.drop_table('place_alias')
    op.drop_index('ix_observation_lookup', table_name='observation')
    op.drop_index(op.f('ix_observation_dataset_id'), table_name='observation')
    op.drop_table('observation')
    op.drop_table('ingest_run')
    op.drop_index(op.f('ix_admin_area_parent_id'), table_name='admin_area')
    op.drop_index('ix_admin_area_name', table_name='admin_area')
    op.drop_index('ix_admin_area_level_active', table_name='admin_area')
    op.drop_index(op.f('ix_admin_area_dataset_id'), table_name='admin_area')
    op.drop_geospatial_index('idx_admin_area_geom', table_name='admin_area', postgresql_using='gist', column_name='geom')
    op.drop_geospatial_table('admin_area')
    op.drop_index(op.f('ix_need_category_sector_id'), table_name='need_category')
    op.drop_table('need_category')
    op.drop_index(op.f('ix_indicator_sector_id'), table_name='indicator')
    op.drop_table('indicator')
    op.drop_table('dataset')
    op.drop_index(op.f('ix_data_gap_sector_id'), table_name='data_gap')
    op.drop_table('data_gap')
    op.drop_table('source')
    op.drop_table('sector')
