from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from connectly.ingest.manifest import ManifestError, all_manifests, load_manifest
from connectly.models import Base
from connectly.taxonomy.seed import seed_reference_data
from connectly.taxonomy.seed_data import SECTORS
from tests.conftest import TEST_DB_URL, alembic_config


def test_models_match_migrations(engine):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = [
            d
            for d in compare_metadata(ctx, Base.metadata)
            if not (d[0] == "remove_table" and d[1].name == "spatial_ref_sys")
        ]
    assert diff == []


def test_downgrade_and_upgrade_round_trip(engine):
    cfg = alembic_config(TEST_DB_URL)
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('admin_area')")).scalar() is None
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('admin_area')")).scalar() == "admin_area"


def test_value_type_constraint_rejects_unknown_values(session):
    seed_reference_data(session)
    session.execute(
        text(
            "INSERT INTO source (key, name) VALUES ('s', 's');"
            "INSERT INTO dataset (key, source_id, title, licence_verified, status) "
            "VALUES ('d', 1, 't', false, 'registered')"
        )
    )
    with pytest.raises(Exception, match="value_type"):
        session.execute(
            text(
                "INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, "
                "value_type, verification_status, dataset_id) "
                "VALUES (1, 'state', 1, '2023', 1.0, 'guess', 'unverified', 1)"
            )
        )


def test_seed_is_idempotent_and_covers_all_sectors(session):
    first = seed_reference_data(session)
    second = seed_reference_data(session)
    assert first == second
    assert session.scalar(text("SELECT count(*) FROM sector")) == 8
    assert session.scalar(text("SELECT count(*) FROM need_category")) == sum(
        len(s["needs"]) for s in SECTORS
    )
    # Seeding defines indicators but never creates values.
    assert session.scalar(text("SELECT count(*) FROM observation")) == 0


def test_shipped_manifests_are_valid():
    manifests = all_manifests()
    assert {"geoboundaries-nga-adm1", "geoboundaries-nga-adm2", "grid3-nga-wards-v4"} <= set(
        manifests
    )
    for m in manifests.values():
        assert m.licence, m.key
        assert m.attribution, m.key
        if m.licence_verified:
            assert m.licence_evidence, f"{m.key}: verified licence needs evidence"


def test_unverified_licence_is_not_marked_commercial():
    m = all_manifests()["grid3-nga-wards-v4"]
    assert m.licence_verified is False
    assert m.commercial_use_allowed is None


def test_invalid_manifest_is_rejected(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("key: x\nkind: admin_boundaries\n")
    with pytest.raises(ManifestError, match="missing keys"):
        load_manifest(p)
