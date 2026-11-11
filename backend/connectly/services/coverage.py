"""Nationwide data coverage, state by state.

Answers, for every state: which layers of evidence exist there, from which dataset. Every
figure is read from the database. A layer counts as covered in a state only when a dataset's
recorded coverage includes that state (ingest/coverage.py); records alone are not enough.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connectly.ingest.coverage import sources_by_state
from connectly.models import Dataset

POPULATION = "population.modelled_total"

# Facility kinds that feed indicators, in display order.
FACILITY_LAYERS = [
    ("health", "Health facilities"),
    ("education", "Schools"),
    ("telecom", "Mobile network sites"),
    ("financial", "Financial access points"),
    ("market", "Markets"),
]


def _datasets(session: Session, table: str, kind: str | None = None) -> list[Dataset]:
    where = "WHERE kind = :k" if kind else ""
    ids = (
        session.execute(text(f"SELECT DISTINCT dataset_id FROM {table} {where}"), {"k": kind})
        .scalars()
        .all()
    )
    return list(session.scalars(select(Dataset).where(Dataset.id.in_(ids)))) if ids else []


def _counts(session: Session, table: str, src: dict[int, Dataset], kind: str | None) -> dict:
    if not src:
        return {}
    kind_sql = "AND kind = :k" if kind else ""
    return dict(
        session.execute(
            text(
                f"""
                SELECT state_id, count(*) FROM {table}
                WHERE (state_id, dataset_id) IN
                      (SELECT * FROM unnest(CAST(:s AS int[]), CAST(:d AS int[]))) {kind_sql}
                GROUP BY state_id
                """
            ),
            {"s": list(src), "d": [ds.id for ds in src.values()], "k": kind},
        ).all()
    )


def national_coverage(session: Session) -> dict[str, Any]:
    states = (
        session.execute(
            text(
                """
            SELECT st.id, st.name,
              (SELECT count(*) FROM admin_area l WHERE l.parent_id = st.id AND l.active) AS lgas,
              (SELECT count(*) FROM admin_area w JOIN admin_area l ON l.id = w.parent_id
                 WHERE l.parent_id = st.id AND w.level = 'ward' AND w.active) AS wards
            FROM admin_area st WHERE st.level = 'state' AND st.active ORDER BY st.name
            """
            )
        )
        .mappings()
        .all()
    )

    ward_sources = dict(
        session.execute(
            text(
                """
                SELECT l.parent_id, string_agg(DISTINCT d.key, ', ')
                FROM admin_area w JOIN admin_area l ON l.id = w.parent_id
                JOIN dataset d ON d.id = w.dataset_id
                WHERE w.level = 'ward' AND w.active GROUP BY l.parent_id
                """
            )
        ).all()
    )
    # Share of a state's active wards that have a modelled population value.
    population = {
        r.state_id: (r.with_value, r.source)
        for r in session.execute(
            text(
                """
                SELECT l.parent_id AS state_id, count(DISTINCT o.geo_id) AS with_value,
                       string_agg(DISTINCT d.key, ', ') AS source
                FROM observation o
                JOIN indicator i ON i.id = o.indicator_id AND i.code = :pop
                JOIN admin_area w ON w.id = o.geo_id AND w.level = 'ward' AND w.active
                JOIN admin_area l ON l.id = w.parent_id
                JOIN dataset d ON d.id = o.dataset_id
                WHERE o.geo_level = 'ward' GROUP BY l.parent_id
                """
            ),
            {"pop": POPULATION},
        )
    }
    # State-level statistics from surveys and official tables (not derived from other data).
    survey = {
        r.geo_id: (r.indicators, r.sources)
        for r in session.execute(
            text(
                """
                SELECT o.geo_id, count(DISTINCT o.indicator_id) AS indicators,
                       string_agg(DISTINCT d.key, ', ') AS sources
                FROM observation o JOIN dataset d ON d.id = o.dataset_id
                WHERE o.geo_level = 'state' AND o.value_type IN ('measured', 'estimated')
                GROUP BY o.geo_id
                """
            )
        )
    }

    point_layers: list[tuple[str, str, dict[int, Dataset], dict]] = []
    for kind, label in FACILITY_LAYERS:
        src = sources_by_state(session, _datasets(session, "facility", kind), "facility")
        point_layers.append((kind, label, src, _counts(session, "facility", src, kind)))
    s_src = sources_by_state(session, _datasets(session, "settlement"), "settlement")
    point_layers.append(
        ("settlements", "Settlements", s_src, _counts(session, "settlement", s_src, None))
    )

    rows = []
    for st in states:
        sid = st["id"]
        pop_n, pop_src = population.get(sid, (0, None))
        sv_n, sv_src = survey.get(sid, (0, None))
        layers = {
            "wards": {
                "covered": st["wards"] > 0,
                "records": st["wards"],
                "source": ward_sources.get(sid),
            },
            "population": {
                "covered": st["wards"] > 0 and pop_n == st["wards"],
                "partial": 0 < pop_n < st["wards"],
                "records": pop_n,
                "source": pop_src,
            },
            "survey": {"covered": sv_n > 0, "records": sv_n, "source": sv_src},
        }
        for code, _label, src, counts in point_layers:
            layers[code] = {
                "covered": sid in src,
                "records": counts.get(sid, 0) if sid in src else 0,
                "source": src[sid].key if sid in src else None,
            }
        rows.append(
            {
                "id": sid,
                "name": st["name"],
                "lgas": st["lgas"],
                "wards": st["wards"],
                "layers": layers,
            }
        )

    layer_defs = [
        ("wards", "Ward boundaries", "wards per state"),
        ("population", "Modelled population", "wards with a value"),
        *[(code, label, "records from the source used there") for code, label, *_ in point_layers],
        ("survey", "State statistics", "indicators from surveys and official tables"),
    ]
    return {
        "states_total": len(rows),
        "layers": [
            {
                "code": code,
                "label": label,
                "count_meaning": meaning,
                "states_covered": sum(1 for r in rows if r["layers"][code]["covered"]),
            }
            for code, label, meaning in layer_defs
        ],
        "states": rows,
    }
