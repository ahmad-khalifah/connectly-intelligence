import pytest
from sqlalchemy import text

from connectly.ingest.boundaries import LoadError, load_boundaries
from tests.conftest import LGAS, STATES, box, feature, write_geojson


def area(session, name):
    return (
        session.execute(
            text(
                "SELECT a.*, p.name AS parent_name FROM admin_area a "
                "LEFT JOIN admin_area p ON p.id = a.parent_id WHERE a.name = :n AND a.active"
            ),
            {"n": name},
        )
        .mappings()
        .one()
    )


def test_loads_hierarchy_and_assigns_parents_spatially(session, synthetic_hierarchy):
    assert synthetic_hierarchy["lga"].rows_loaded == 6
    counts = dict(
        session.execute(text("SELECT level, count(*) FROM admin_area GROUP BY level")).all()
    )
    assert counts == {"country": 1, "state": 2, "lga": 6}

    assert area(session, "West")["parent_name"] == "Testland"
    assert area(session, "West North")["parent_name"] == "West"
    assert area(session, "East South")["parent_name"] == "East"
    assert area(session, "West North")["parent_overlap"] == pytest.approx(1.0)


def test_straddling_area_goes_to_largest_overlap_and_is_flagged(session, synthetic_hierarchy):
    border = area(session, "Border")
    assert border["parent_name"] == "West"
    # 1.0° of its 1.25° width lies in West.
    assert border["parent_overlap"] == pytest.approx(0.8, abs=0.01)
    warnings = " ".join(synthetic_hierarchy["lga"].warnings)
    assert "Border" in warnings and "less than 95%" in warnings


def test_provenance_is_recorded(session, synthetic_hierarchy):
    ds = session.execute(text("SELECT * FROM dataset WHERE key = 't-lgas'")).mappings().one()
    assert ds["status"] == "loaded"
    assert ds["licence"] == "CC BY 4.0"
    assert ds["record_count"] == 6
    assert len(ds["file_sha256"]) == 64
    assert ds["extra"]["attribution"] == "Synthetic test data"
    run = (
        session.execute(text("SELECT * FROM ingest_run WHERE dataset_id = :d"), {"d": ds["id"]})
        .mappings()
        .one()
    )
    assert run["status"] == "succeeded"
    assert (run["rows_read"], run["rows_loaded"], run["rows_rejected"]) == (6, 6, 0)


def test_area_is_computed_in_square_km(session, synthetic_hierarchy):
    # 1°×2° near 10°N ≈ 109.6 km × 221 km ≈ 24,000 km².
    km2 = area(session, "West North")["area_km2"]
    assert 23_000 < km2 < 25_500


def test_aliases_are_stored(session, synthetic_hierarchy):
    aliases = (
        session.execute(
            text(
                "SELECT p.alias FROM place_alias p JOIN admin_area a ON a.id = p.admin_area_id "
                "WHERE a.name = 'West'"
            )
        )
        .scalars()
        .all()
    )
    assert aliases == ["T-W"]


def test_identical_reload_is_skipped_and_forced_reload_keeps_ids(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    m = make_manifest("t-lgas", "lga")
    path = tmp_path / "t-lgas.geojson"
    ids_before = (
        session.execute(text("SELECT id FROM admin_area WHERE level='lga'")).scalars().all()
    )

    skipped = load_boundaries(session, m, file=path)
    assert skipped.status == "skipped"

    forced = load_boundaries(session, m, file=path, force=True)
    assert forced.status == "succeeded"
    ids_after = session.execute(text("SELECT id FROM admin_area WHERE level='lga'")).scalars().all()
    assert sorted(ids_before) == sorted(ids_after)


def test_full_reload_removes_areas_dropped_from_file(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    path = write_geojson(tmp_path / "t-lgas.geojson", LGAS[:-1])
    report = load_boundaries(session, make_manifest("t-lgas", "lga"), file=path)
    assert any("removed 1" in w for w in report.warnings)
    assert session.scalar(text("SELECT count(*) FROM admin_area WHERE level='lga'")) == 5


def test_reprojects_to_wgs84(session, tmp_path, make_manifest):
    # West state's corners in Web Mercator (EPSG:3857).
    merc = box(1113194.9, 781182.2, 1335833.9, 1232106.8)
    path = write_geojson(tmp_path / "m.geojson", [feature("M", "M1", merc)], crs="EPSG:3857")
    report = load_boundaries(session, make_manifest("t-merc", "state"), file=path)
    assert any("reprojected" in w for w in report.warnings)
    x0, y0 = session.execute(
        text("SELECT ST_XMin(geom), ST_YMin(geom) FROM admin_area WHERE name='M'")
    ).one()
    assert x0 == pytest.approx(10.0, abs=1e-4)
    assert y0 == pytest.approx(7.0, abs=1e-3)


def test_rejects_file_without_crs(session, tmp_path, make_manifest):
    path = tmp_path / "nocrs.gpkg"
    import geopandas as gpd
    from shapely.geometry import shape

    gpd.GeoDataFrame(
        {"shapeName": ["X"], "shapeID": ["X1"]}, geometry=[shape(box(10, 7, 11, 8))]
    ).to_file(path)
    with pytest.raises(LoadError, match="no coordinate reference system"):
        load_boundaries(session, make_manifest("t-nocrs", "state"), file=path)


def test_rejects_data_outside_nigeria(session, tmp_path, make_manifest):
    path = write_geojson(tmp_path / "far.geojson", [feature("Far", "F1", box(30, 50, 31, 51))])
    with pytest.raises(LoadError, match="outside Nigeria"):
        load_boundaries(session, make_manifest("t-far", "state"), file=path)


def test_missing_field_lists_real_columns(session, tmp_path, make_manifest):
    path = write_geojson(tmp_path / "f.geojson", STATES)
    m = make_manifest("t-fields", "state", fields={"name": ["wardname"], "code": ["shapeID"]})
    with pytest.raises(LoadError, match="Columns found: .*shapeName"):
        load_boundaries(session, m, file=path)


def test_repairs_invalid_and_rejects_empty_geometry(session, tmp_path, make_manifest):
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[10, 7], [11, 8], [11, 7], [10, 8], [10, 7]]],
    }
    feats = [
        feature("Bowtie", "B1", bowtie),
        feature("NoGeom", "B2", None),
        feature(None, "B3", box(10, 7, 10.5, 7.5)),
        feature("Fine", "B4", box(12, 7, 13, 8)),
    ]
    path = write_geojson(tmp_path / "b.geojson", feats)
    report = load_boundaries(session, make_manifest("t-bad", "state"), file=path)
    assert report.rows_loaded == 2
    assert report.rows_rejected == 2
    assert any("repaired 1" in w for w in report.warnings)
    valid = session.scalar(text("SELECT bool_and(ST_IsValid(geom)) FROM admin_area"))
    assert valid is True


def test_duplicate_codes_fail(session, tmp_path, make_manifest):
    feats = [feature("A", "DUP", box(10, 7, 11, 8)), feature("B", "DUP", box(11, 7, 12, 8))]
    path = write_geojson(tmp_path / "d.geojson", feats)
    with pytest.raises(LoadError, match="duplicate codes"):
        load_boundaries(session, make_manifest("t-dup", "state"), file=path)


def test_within_state_keeps_only_areas_inside(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    wards = [
        feature("W in West", "W1", box(10.1, 9.1, 10.4, 9.4)),
        feature("W in East", "W2", box(13.1, 7.1, 13.4, 7.4)),
    ]
    path = write_geojson(tmp_path / "w.geojson", wards)
    report = load_boundaries(
        session, make_manifest("t-wards", "ward"), file=path, within_state="west"
    )
    assert report.rows_loaded == 1
    assert report.rows_out_of_scope == 1
    assert area(session, "W in West")["parent_name"] == "West North"


def test_within_state_unknown_name_lists_states(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    path = write_geojson(tmp_path / "w.geojson", [feature("W", "W1", box(10.1, 9.1, 10.4, 9.4))])
    with pytest.raises(LoadError, match="Available: .*East.*West"):
        load_boundaries(session, make_manifest("t-wards", "ward"), file=path, within_state="Kano")


def test_second_dataset_is_not_activated_automatically(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    path = write_geojson(tmp_path / "s2.geojson", STATES)
    report = load_boundaries(session, make_manifest("t-states-v2", "state"), file=path)
    assert report.active is False
    assert any("NOT active" in w for w in report.warnings)
    active_ds = (
        session.execute(
            text(
                "SELECT DISTINCT d.key FROM admin_area a JOIN dataset d ON d.id = a.dataset_id "
                "WHERE a.level = 'state' AND a.active"
            )
        )
        .scalars()
        .all()
    )
    assert active_ds == ["t-states"]


def test_switching_active_dataset_relinks_children(
    session, synthetic_hierarchy, tmp_path, make_manifest
):
    path = write_geojson(tmp_path / "s2.geojson", STATES)
    report = load_boundaries(
        session, make_manifest("t-states-v2", "state"), file=path, activate="yes"
    )
    assert report.active is True
    parent_ds = (
        session.execute(
            text(
                "SELECT DISTINCT d.key FROM admin_area c JOIN admin_area p ON p.id = c.parent_id "
                "JOIN dataset d ON d.id = p.dataset_id WHERE c.level = 'lga'"
            )
        )
        .scalars()
        .all()
    )
    assert parent_ds == ["t-states-v2"]
    status = session.scalar(text("SELECT status FROM dataset WHERE key = 't-states'"))
    assert status == "superseded"


def test_rename_keeps_source_name_and_alias(session, tmp_path, make_manifest):
    path = write_geojson(
        tmp_path / "c.geojson", [feature("Republic of Testland", "C9", box(10, 7, 14, 11))]
    )
    m = make_manifest("t-rename", "country", rename={"Republic of Testland": "Testland"})
    load_boundaries(session, m, file=path)
    row = area(session, "Testland")
    assert row["source_name"] == "Republic of Testland"
    alias = session.scalar(text("SELECT alias FROM place_alias"))
    assert alias == "Republic of Testland"


def test_missing_manual_file_is_reported_not_failed(session, make_manifest):
    from connectly.ingest.boundaries import FileNotProvidedError

    with pytest.raises(FileNotProvidedError, match="downloaded by hand"):
        load_boundaries(session, make_manifest("t-manual", "ward"))
