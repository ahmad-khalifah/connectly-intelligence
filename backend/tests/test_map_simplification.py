"""Map boundaries must keep shared borders shared after simplification.

Two states meet along a jagged border. Simplifying each state on its own makes them overlap
and leave gaps on the map; the map endpoint must not.
"""

import math

import pytest
import shapely
from fastapi.testclient import TestClient
from shapely.geometry import shape

from connectly.api.main import create_app
from connectly.api.routers.geography import simplify_coverage
from connectly.ingest.boundaries import load_boundaries
from tests.conftest import auth_header, feature, make_user, write_geojson


def jagged_border(n: int = 400) -> list[list[float]]:
    """A wavy north–south line at about lon 12, from lat 7 to lat 11."""
    return [
        [12 + 0.01 * math.sin(i * 0.7) + 0.004 * math.sin(i * 2.3), 7 + 4 * i / n]
        for i in range(n + 1)
    ]


def two_states() -> list[dict]:
    border = jagged_border()
    west = [[10, 7], *border, [10, 11], [10, 7]]
    east = [*border, [14, 11], [14, 7], border[0]]
    return [
        feature("West", "S1", {"type": "Polygon", "coordinates": [west]}),
        feature("East", "S2", {"type": "Polygon", "coordinates": [east]}),
    ]


@pytest.fixture
def client(engine, session, tmp_path, make_manifest):
    path = write_geojson(tmp_path / "s.geojson", two_states())
    load_boundaries(session, make_manifest("t-jagged", "state"), file=path)
    session.commit()
    c = TestClient(create_app(engine))
    c.headers.update(auth_header(make_user(session)))
    return c


def test_map_layer_keeps_shared_borders_after_simplification(client):
    fc = client.get("/api/v1/geojson", params={"level": "state", "tolerance": 0.02}).json()
    shapes = {f["properties"]["name"]: shape(f["geometry"]) for f in fc["features"]}
    west, east = shapes["West"], shapes["East"]
    # The simplification really ran (far fewer vertices than the 400-point border)...
    assert shapely.get_num_coordinates(west) < 100
    # ...and the two states still meet exactly: no overlap, no gap.
    assert west.intersection(east).area == pytest.approx(0, abs=1e-9)
    assert west.union(east).area == pytest.approx(16.0, rel=1e-6)


def test_per_area_simplification_would_have_overlapped():
    """Documents the defect this guards against."""
    west, east = (shape(f["geometry"]) for f in two_states())
    separately = [west.simplify(0.02), east.simplify(0.02)]
    together = simplify_coverage([west, east], 0.02)
    assert separately[0].intersection(separately[1]).area > 1e-4
    assert together[0].intersection(together[1]).area == pytest.approx(0, abs=1e-9)


def test_zero_tolerance_returns_full_detail(client):
    fc = client.get("/api/v1/geojson", params={"level": "state", "tolerance": 0}).json()
    west = shape(next(f for f in fc["features"] if f["properties"]["name"] == "West")["geometry"])
    assert shapely.get_num_coordinates(west) > 400
