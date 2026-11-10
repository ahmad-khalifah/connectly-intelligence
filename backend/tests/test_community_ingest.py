"""Milestone 2 ingestion: wards with observations, points, OSM, tables, DHS, derivations.

All inputs are synthetic and only touch the connectly_test database.
"""

import gzip
import json
import zipfile

import pytest
from sqlalchemy import text

from connectly.ingest import derive, observations, osm, points, tables
from connectly.ingest.boundaries import LoadError, load_boundaries
from connectly.ingest.fetch import FetchError, extract_member
from connectly.taxonomy.seed import seed_reference_data
from tests.conftest import box, feature, write_geojson


@pytest.fixture
def seeded(session, synthetic_hierarchy):
    seed_reference_data(session)
    session.commit()
    return session


@pytest.fixture
def wards(seeded, tmp_path, make_manifest):
    """Two wards in West North (codes T-W) and one in East South (T-E), with population."""
    feats = [
        feature("Alpha", "W1", box(10.0, 9.0, 10.5, 11.0), st="T-W", pop=10000, lo=8000, hi=12000),
        feature("Beta", "W2", box(10.5, 9.0, 11.0, 11.0), st="T-W", pop=20000, lo=15000, hi=26000),
        feature("Gamma", "W3", box(12.0, 7.0, 14.0, 9.0), st="T-W", pop=5000, lo=4000, hi=6000),
    ]
    path = write_nocrs_gpkg(tmp_path / "wards.gpkg", feats)
    m = make_manifest(
        "t-wards",
        "ward",
        assume_crs="EPSG:4326",
        assume_crs_reason="test",
        checks=[
            {
                "type": "ancestor_code",
                "attribute": "st",
                "ancestor_level": "state",
                "alias_template": "{value}",
            }
        ],
        observations=[
            {
                "indicator": "population.modelled_total",
                "value": "pop",
                "lower": "lo",
                "upper": "hi",
                "value_type": "modelled",
                "period": "2019",
            }
        ],
    )
    report = load_boundaries(seeded, m, file=path)
    seeded.commit()
    return report


def write_nocrs_gpkg(path, feats):
    """A GeoPackage with no CRS (GeoJSON is lon/lat by specification, so it cannot test this)."""
    import geopandas as gpd
    from shapely.geometry import shape

    gpd.GeoDataFrame(
        [f["properties"] for f in feats], geometry=[shape(f["geometry"]) for f in feats]
    ).to_file(path)
    return path


def obs(session, code, level=None):
    sql = (
        "SELECT a.name, o.value, o.lower_bound, o.upper_bound, o.value_type, o.geo_level "
        "FROM observation o JOIN indicator i ON i.id = o.indicator_id "
        "JOIN admin_area a ON a.id = o.geo_id WHERE i.code = :c"
    )
    if level:
        sql += " AND o.geo_level = :l"
    return {
        r.name: r for r in session.execute(text(sql + " ORDER BY a.name"), {"c": code, "l": level})
    }


def test_assumed_crs_and_observations_with_bounds(seeded, wards):
    assert any("assumed EPSG:4326" in w for w in wards.warnings)
    pop = obs(seeded, "population.modelled_total", "ward")
    assert pop["Alpha"].value == 10000
    assert (pop["Beta"].lower_bound, pop["Beta"].upper_bound) == (15000, 26000)
    assert pop["Alpha"].value_type == "modelled"


def test_ancestor_code_check_reports_mismatch(seeded, wards):
    # Gamma says T-W but lies in East.
    msg = [w for w in wards.warnings if w.startswith("check:")]
    assert msg and "1 of 3" in msg[0] and "Gamma (T-W) in East" in msg[0]


def test_missing_crs_without_assumption_fails(seeded, tmp_path, make_manifest):
    path = write_nocrs_gpkg(tmp_path / "w.gpkg", [feature("A", "A", box(10, 9, 11, 10))])
    with pytest.raises(LoadError, match="assume_crs"):
        load_boundaries(seeded, make_manifest("t-nocrs2", "ward"), file=path)


def test_aggregate_sum_is_complete_or_skipped(seeded, wards):
    from connectly.models import Dataset

    src = seeded.query(Dataset).filter_by(key="t-wards").one()
    r = observations.aggregate_sum(seeded, "population.modelled_total", src, "ward", "lga")
    # West North has both its wards; East South has Gamma; the other LGAs have no wards.
    lga = obs(seeded, "population.modelled_total", "lga")
    assert lga["West North"].value == 30000
    assert lga["East South"].value == 5000
    assert lga["West North"].value_type == "derived"
    assert r.stored == 2
    ds = (
        seeded.query(Dataset)
        .filter_by(key=r and "derived-sum-population.modelled_total-ward-to-lga")
        .one()
    )
    assert ds.extra["inputs"] == ["t-wards"]
    assert ds.licence == "Derived from: CC BY 4.0"


# --------------------------------------------------------------------------- points


def points_manifest(make_manifest, key, target="facility", **points_cfg):
    return make_manifest(
        key,
        None,
        kind="facilities" if target == "facility" else "settlements",
        fields={"name": ["name"], "code": ["id"], "subtype": ["type"], "status": ["status"]},
        points={"target": target, **points_cfg},
    )


def test_facilities_from_geojson_linked_to_ward(seeded, wards, tmp_path, make_manifest):
    pts = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "H1",
                    "name": "Clinic A",
                    "type": "PHC",
                    "status": "Functional",
                },
                "geometry": {"type": "Point", "coordinates": [10.2, 10.0]},
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "H2",
                    "name": "Clinic B",
                    "type": "PHC",
                    "status": "Not functional",
                },
                "geometry": {"type": "Point", "coordinates": [13.0, 8.0]},
            },
        ],
    }
    path = tmp_path / "hf.geojson"
    path.write_text(json.dumps(pts))
    m = points_manifest(make_manifest, "t-health", facility_kind="health")
    report = points.load_points(seeded, m, file=path)
    assert report.rows_loaded == 2
    row = seeded.execute(
        text(
            "SELECT f.name, w.name AS ward, l.name AS lga, s.name AS state, f.operational_status "
            "FROM facility f JOIN admin_area w ON w.id = f.ward_id JOIN admin_area l ON l.id = f.lga_id "
            "JOIN admin_area s ON s.id = f.state_id WHERE f.source_code = 'H1'"
        )
    ).one()
    assert (row.ward, row.lga, row.state) == ("Alpha", "West North", "West")
    assert row.operational_status == "Functional"


def test_opencellid_style_csv_without_header(seeded, wards, tmp_path, make_manifest):
    lines = [
        "GSM,621,20,100,1,0,10.20001,10.00001,1000,5,1,0,0,0",
        "GSM,621,20,100,2,0,10.20002,10.00002,1000,5,1,0,0,0",  # same site, same radio
        "LTE,621,20,100,3,0,10.20001,10.00001,1000,5,1,0,0,0",  # same site, other radio
        "UMTS,624,1,1,4,0,10.7,10.5,1000,5,1,0,0,0",  # other country code: filtered out
        "GSM,621,20,100,5,0,,,1000,5,1,0,0,0",  # no coordinates
    ]
    path = tmp_path / "621.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")
    m = make_manifest(
        "t-ocid",
        None,
        kind="facilities",
        fields={"code": ["cell"], "subtype": ["radio"]},
        points={
            "target": "facility",
            "facility_kind": "telecom",
            "lon": ["lon"],
            "lat": ["lat"],
            "csv_names": [
                "radio",
                "mcc",
                "net",
                "area",
                "cell",
                "unit",
                "lon",
                "lat",
                "range",
                "samples",
                "changeable",
                "created",
                "updated",
                "averageSignal",
            ],
            "filters": [{"column": "mcc", "in": ["621"]}],
            "code_compose": ["radio", "mcc", "net", "area", "cell"],
            "dedupe_round": 4,
            "dedupe_by": ["radio"],
        },
    )
    report = points.load_points(seeded, m, file=path)
    assert report.rows_read == 5
    assert report.rows_rejected == 1
    assert report.rows_loaded == 2  # GSM site + LTE site
    assert any("kept 3 of 4" in w for w in report.warnings)


def test_settlement_extents_get_representative_point(seeded, wards, tmp_path, make_manifest):
    path = write_geojson(
        tmp_path / "s.geojson",
        [feature("Kauye", "S1", box(10.6, 9.6, 10.7, 9.7), type="built-up")],
    )
    m = make_manifest(
        "t-ext",
        None,
        kind="settlements",
        fields={"name": ["shapeName"], "code": ["shapeID"], "settlement_type": ["type"]},
        points={"target": "settlement"},
    )
    points.load_points(seeded, m, file=path)
    r = seeded.execute(
        text(
            "SELECT s.name, s.settlement_type, ST_Within(s.point, s.extent) AS inside, w.name AS ward "
            "FROM settlement s JOIN admin_area w ON w.id = s.ward_id"
        )
    ).one()
    assert (r.name, r.settlement_type, r.inside, r.ward) == ("Kauye", "built-up", True, "Beta")


def test_facility_manifest_needs_a_kind(seeded, wards, tmp_path, make_manifest):
    path = write_geojson(tmp_path / "x.geojson", [feature("X", "X1", box(10, 9, 10.1, 9.1))])
    m = make_manifest(
        "t-nokind",
        None,
        kind="facilities",
        fields={"code": ["shapeID"]},
        points={"target": "facility"},
    )
    with pytest.raises(LoadError, match="facility_kind"):
        points.load_points(seeded, m, file=path)


OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="10.1" lon="10.1" version="1"><tag k="amenity" v="bank"/><tag k="name" v="Test Bank"/></node>
  <node id="2" lat="10.2" lon="10.2" version="1"><tag k="amenity" v="atm"/></node>
  <node id="3" lat="10.3" lon="10.3" version="1"><tag k="amenity" v="cafe"/></node>
  <node id="4" lat="10.4" lon="10.6" version="1"><tag k="man_made" v="mast"/><tag k="tower:type" v="communication"/></node>
  <node id="5" lat="10.5" lon="10.7" version="1"><tag k="man_made" v="mast"/><tag k="tower:type" v="lighting"/></node>
</osm>
"""


def test_osm_tag_rules(seeded, wards, tmp_path, make_manifest):
    path = tmp_path / "t.osm"
    path.write_text(OSM_XML)
    m = make_manifest(
        "t-osm",
        None,
        kind="osm_facilities",
        osm={
            "layers": ["points"],
            "rules": [
                {"tag": "amenity", "values": ["bank"], "kind": "financial", "subtype": "bank"},
                {"tag": "amenity", "values": ["atm"], "kind": "financial", "subtype": "atm"},
                {
                    "tag": "man_made",
                    "values": ["mast"],
                    "also": {"tower:type": ["communication"]},
                    "kind": "telecom",
                },
            ],
        },
    )
    report = osm.load_osm(seeded, m, file=path)
    rows = dict(
        seeded.execute(text("SELECT source_code, kind FROM facility ORDER BY source_code")).all()
    )
    assert rows == {"node/1": "financial", "node/2": "financial", "node/4": "telecom"}
    assert report.rows_loaded == 3
    name = seeded.scalar(text("SELECT name FROM facility WHERE source_code = 'node/1'"))
    assert name == "Test Bank"


def test_parse_other_tags():
    tags = osm.parse_other_tags('"amenity"=>"bank","name:ha"=>"Banki \\"A\\""')
    assert tags == {"amenity": "bank", "name:ha": 'Banki "A"'}


# --------------------------------------------------------------------------- tables / DHS


def table_manifest(make_manifest, key="t-table"):
    return make_manifest(
        key,
        None,
        kind="indicator_table",
        table={"geo_level": "state", "allowed_indicators": ["finance.formal_inclusion_adults_pct"]},
    )


def test_indicator_table_loads_valid_rows(seeded, tmp_path, make_manifest):
    path = tmp_path / "t.csv"
    path.write_text(
        "area,indicator_code,period,value,lower,upper,value_type,source_reference\n"
        "West,finance.formal_inclusion_adults_pct,2023,61.5,,,measured,Table 4 p.12\n"
        "t-e,finance.formal_inclusion_adults_pct,2023,40,,,,Table 4 p.12\n"
    )
    r = tables.load_indicator_table(seeded, table_manifest(make_manifest), file=path)
    assert r.rows_loaded == 2
    vals = obs(seeded, "finance.formal_inclusion_adults_pct")
    assert vals["West"].value == 61.5 and vals["East"].value == 40  # alias T-E resolved


@pytest.mark.parametrize(
    "row,problem",
    [
        ("Kano,finance.formal_inclusion_adults_pct,2023,50,,,,p.1", "unknown or ambiguous"),
        ("West,health.facilities_per_10k,2023,5,,,,p.1", "not allowed"),
        ("West,finance.formal_inclusion_adults_pct,2023,150,,,,p.1", "outside 0–100"),
        ("West,finance.formal_inclusion_adults_pct,2023,50,,,,", "no source reference"),
        (
            "West,finance.formal_inclusion_adults_pct,2023,50,,,ai_generated,p.1",
            "invalid value_type",
        ),
    ],
)
def test_indicator_table_rejects_whole_file_on_any_bad_row(
    seeded, tmp_path, make_manifest, row, problem
):
    path = tmp_path / "t.csv"
    path.write_text(
        "area,indicator_code,period,value,lower,upper,value_type,source_reference\n"
        "East,finance.formal_inclusion_adults_pct,2023,40,,,,Table 4\n" + row + "\n"
    )
    with pytest.raises(LoadError, match=problem):
        tables.load_indicator_table(seeded, table_manifest(make_manifest), file=path)
    assert seeded.scalar(text("SELECT count(*) FROM observation")) == 0


def test_empty_template_explains_what_to_do(seeded, tmp_path, make_manifest):
    path = tmp_path / "t.csv"
    path.write_text(
        "# comment\narea,indicator_code,period,value,lower,upper,value_type,source_reference\n"
    )
    with pytest.raises(LoadError, match="no data rows"):
        tables.load_indicator_table(seeded, table_manifest(make_manifest), file=path)


def dhs_manifest(make_manifest, label="electricity"):
    return make_manifest(
        "t-dhs",
        None,
        kind="dhs_api",
        download={"mode": "api"},
        api={
            "base_url": "https://api.dhsprogram.com/rest/dhs/data",
            "survey_id": "XX2023DHS",
            "indicators": [
                {
                    "dhs_id": "HC_ELEC_H_ELC",
                    "expect_label_contains": label,
                    "indicator": "energy.households_electricity_pct",
                }
            ],
        },
    )


DHS_SYNTHETIC = {
    "Data": [
        {
            "IndicatorId": "HC_ELEC_H_ELC",
            "Indicator": "Households with electricity",
            "CharacteristicLabel": "..West",
            "Value": 55.0,
            "CILow": 50.1,
            "CIHigh": 59.9,
            "SurveyYearLabel": "2023-24",
            "SurveyId": "XX2023DHS",
            "ByVariableLabel": "",
        },
        {
            "IndicatorId": "HC_ELEC_H_ELC",
            "Indicator": "Households with electricity",
            "CharacteristicLabel": "Zone : East",
            "Value": 30.0,
            "CILow": "",
            "CIHigh": "",
            "SurveyYearLabel": "2023-24",
            "SurveyId": "XX2023DHS",
            "ByVariableLabel": "",
        },
        {
            "IndicatorId": "HC_ELEC_H_ELC",
            "Indicator": "Households with electricity",
            "CharacteristicLabel": "North Zone",
            "Value": 45.0,
            "SurveyYearLabel": "2023-24",
            "SurveyId": "XX2023DHS",
            "ByVariableLabel": "",
        },
        {
            "IndicatorId": "HC_ELEC_H_ELC",
            "Indicator": "Households with electricity",
            "CharacteristicLabel": "..West",
            "Value": 80.0,
            "SurveyYearLabel": "2023-24",
            "SurveyId": "XX2023DHS",
            "ByVariableLabel": "Urban",
        },
    ]
}


def test_dhs_loads_state_totals_with_intervals(seeded, tmp_path, make_manifest):
    path = tmp_path / "dhs.json"
    path.write_text(json.dumps(DHS_SYNTHETIC))
    r = tables.load_dhs(seeded, dhs_manifest(make_manifest), file=path)
    vals = obs(seeded, "energy.households_electricity_pct")
    assert r.rows_loaded == 2
    assert vals["West"].value == 55.0 and vals["West"].lower_bound == 50.1
    assert vals["East"].value == 30.0 and vals["East"].lower_bound is None
    assert any("zones" in w for w in r.warnings)


def test_dhs_label_mismatch_fails(seeded, tmp_path, make_manifest):
    path = tmp_path / "dhs.json"
    path.write_text(json.dumps(DHS_SYNTHETIC))
    with pytest.raises(LoadError, match="does not contain 'mobile'"):
        tables.load_dhs(seeded, dhs_manifest(make_manifest, label="mobile"), file=path)


# --------------------------------------------------------------------------- derive


def load_health(seeded, tmp_path, make_manifest, within_state=None):
    pts = [
        ("H1", 10.25, 10.0, "PHC", "Functional"),
        ("H2", 10.3, 10.1, "PHC", None),
        ("H3", 10.75, 10.0, "Pharmacy", None),  # excluded from health derivations
        ("H4", 10.8, 10.2, "PHC", "Non-functional"),  # excluded
        ("H5", 13.0, 8.0, "PHC", None),  # in East
    ]
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": c, "name": c, "type": t, "status": s},
                "geometry": {"type": "Point", "coordinates": [x, y]},
            }
            for c, x, y, t, s in pts
        ],
    }
    path = tmp_path / "h.geojson"
    path.write_text(json.dumps(fc))
    m = points_manifest(make_manifest, "t-hf", facility_kind="health")
    points.load_points(seeded, m, file=path, within_state=within_state)


def test_derived_per_10k_and_nearest(seeded, wards, tmp_path, make_manifest):
    load_health(seeded, tmp_path, make_manifest)
    d = {x.indicator: x for x in derive.DERIVATIONS}
    derive.run_derivation(seeded, d["health.facilities_per_10k"])
    derive.run_derivation(seeded, d["health.nearest_facility_km_ward_point"])
    per = obs(seeded, "health.facilities_per_10k", "ward")
    assert per["Alpha"].value == pytest.approx(2.0)  # 2 working PHCs / 10,000 people
    assert per["Beta"].value == 0  # pharmacy and non-functional excluded
    assert per["Alpha"].value_type == "derived"
    near = obs(seeded, "health.nearest_facility_km_ward_point", "ward")
    assert near["Alpha"].value < near["Beta"].value


def test_derivations_respect_dataset_coverage(seeded, wards, tmp_path, make_manifest):
    load_health(seeded, tmp_path, make_manifest, within_state="West")
    d = {x.indicator: x for x in derive.DERIVATIONS}
    derive.run_derivation(seeded, d["health.facilities_per_10k"])
    per = obs(seeded, "health.facilities_per_10k", "ward")
    # Gamma is in East, which this dataset does not cover: no value, not zero.
    assert "Gamma" not in per and "Alpha" in per


def test_derivation_skips_without_inputs(seeded, wards):
    d = {x.indicator: x for x in derive.DERIVATIONS}
    r = derive.run_derivation(seeded, d["connectivity.sites_per_10k"])
    assert r.skipped_reason == "no telecom facilities loaded"


def test_derivation_is_idempotent(seeded, wards, tmp_path, make_manifest):
    load_health(seeded, tmp_path, make_manifest)
    d = {x.indicator: x for x in derive.DERIVATIONS}["health.facilities_per_10k"]
    derive.run_derivation(seeded, d)
    first = seeded.scalar(text("SELECT count(*) FROM observation"))
    derive.run_derivation(seeded, d)
    assert seeded.scalar(text("SELECT count(*) FROM observation")) == first


# --------------------------------------------------------------------------- fetch


def test_extract_member_and_refuse_unsafe(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data.topojson", "{}")
    out = extract_member(z, "data.topojson", tmp_path)
    assert out.read_text() == "{}"
    with pytest.raises(FetchError, match="unsafe"):
        extract_member(z, "../evil.txt", tmp_path)
    with pytest.raises(FetchError, match="no member"):
        extract_member(z, "other.json", tmp_path)


def test_checksum_mismatch_deletes_download(tmp_path, monkeypatch, make_manifest):
    from connectly.ingest import fetch as fetch_mod

    def fake_download(url, dest, timeout):
        dest.write_text("tampered")

    monkeypatch.setattr(fetch_mod, "_download", fake_download)
    m = make_manifest(
        "t-sum",
        "state",
        download={
            "mode": "http",
            "url": "https://example.org/x.geojson",
            "file_name": "x.geojson",
            "sha256": "0" * 64,
        },
    )
    with pytest.raises(FetchError, match="checksum mismatch"):
        fetch_mod.fetch(m, raw_dir=tmp_path)
    assert not (tmp_path / "t-sum" / "x.geojson").exists()
