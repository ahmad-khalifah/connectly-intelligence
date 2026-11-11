"""Derived indicators: computed from loaded datasets, never typed in.

Each derivation:
  * produces values only in states some loaded dataset covers (a dataset loaded for one
    state never produces "0 clinics" for another), and uses exactly one dataset per state
    (see ingest/coverage.py), so overlapping sources are never double-counted,
  * writes observations with value_type "derived" into its own derived dataset, which
    lists every input dataset and inherits their licences,
  * replaces its previous output, so re-running is idempotent.

Run with `connectly derive` after loading facilities, settlements or population.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connectly.ingest.coverage import sources_by_state
from connectly.ingest.observations import derived_dataset, indicator_id
from connectly.models import Dataset

POPULATION = "population.modelled_total"
# Only records from the dataset chosen for their state (ingest/coverage.py).
FACILITY_SOURCE = (
    "(f.state_id, f.dataset_id) IN "
    "(SELECT * FROM unnest(CAST(:fsrc_states AS int[]), CAST(:fsrc_ds AS int[])))"
)
SETTLEMENT_SOURCE = (
    "(s.state_id, s.dataset_id) IN "
    "(SELECT * FROM unnest(CAST(:ssrc_states AS int[]), CAST(:ssrc_ds AS int[])))"
)
# Facilities whose published status says they are not operating are excluded.
NON_FUNCTIONAL = (
    "(lower(coalesce(f.operational_status, '')) ~ '(non|not)[ -_]?functional|closed|abandoned')"
)


@dataclass
class Derivation:
    indicator: str
    kind: str  # per_10k | nearest_km | density | settlements_beyond
    facility_kind: str | None = None
    exclude_subtypes: tuple[str, ...] = ()
    levels: tuple[str, ...] = ("ward", "lga", "state")
    threshold_km: float | None = None


DERIVATIONS = [
    Derivation("population.density_per_km2", "density"),
    Derivation("health.facilities_per_10k", "per_10k", "health", ("pharmacy",)),
    Derivation(
        "health.nearest_facility_km_ward_point", "nearest_km", "health", ("pharmacy",), ("ward",)
    ),
    Derivation(
        "health.settlements_over_5km_pct",
        "settlements_beyond",
        "health",
        ("pharmacy",),
        ("ward",),
        5.0,
    ),
    Derivation("connectivity.sites_per_10k", "per_10k", "telecom"),
    Derivation("connectivity.nearest_tower_km_ward_point", "nearest_km", "telecom", (), ("ward",)),
    Derivation("finance.access_points_per_10k", "per_10k", "financial"),
    Derivation(
        "finance.nearest_access_point_km_ward_point", "nearest_km", "financial", (), ("ward",)
    ),
    Derivation("education.schools_per_10k", "per_10k", "education"),
    Derivation("commerce.markets_per_10k", "per_10k", "market"),
]


@dataclass
class DeriveResult:
    indicator: str
    stored: dict[str, int] = field(default_factory=dict)
    skipped_reason: str | None = None


def facility_datasets(session: Session, kind: str) -> list[Dataset]:
    ids = (
        session.execute(
            text("SELECT DISTINCT dataset_id FROM facility WHERE kind = :k"), {"k": kind}
        )
        .scalars()
        .all()
    )
    if not ids:
        return []
    return list(session.scalars(select(Dataset).where(Dataset.id.in_(ids))))


def population_dataset(session: Session) -> Dataset | None:
    ds_id = session.scalar(
        text(
            """
            SELECT o.dataset_id FROM observation o JOIN indicator i ON i.id = o.indicator_id
            WHERE i.code = :c AND o.geo_level = 'ward' LIMIT 1
            """
        ),
        {"c": POPULATION},
    )
    return session.get(Dataset, ds_id) if ds_id else None


def _subtype_filter(d: Derivation) -> str:
    if not d.exclude_subtypes:
        return ""
    quoted = ", ".join(f"'{s}'" for s in d.exclude_subtypes)  # constants defined above
    return f"AND coalesce(lower(f.subtype), '') NOT IN ({quoted})"


def _area_scope_sql(level: str) -> str:
    """SQL expression giving the state id of an area `a` at `level`."""
    return {
        "state": "a.id",
        "lga": "a.parent_id",
        "ward": "(SELECT parent_id FROM admin_area WHERE id = a.parent_id)",
    }[level]


def _area_facility_column(level: str) -> str:
    return {"state": "state_id", "lga": "lga_id", "ward": "ward_id"}[level]


def run_derivation(session: Session, d: Derivation, as_of: date | None = None) -> DeriveResult:
    as_of = as_of or date.today()
    period = f"as of {as_of.isoformat()}"
    result = DeriveResult(d.indicator)
    ind = indicator_id(session, d.indicator)
    pop_ds = population_dataset(session)
    inputs: list[Dataset] = []
    states: list[int] = []

    if d.kind in ("per_10k", "density") and pop_ds is None:
        result.skipped_reason = "no modelled population loaded"
        return result
    fac_src: dict[int, Dataset] = {}
    set_src: dict[int, Dataset] = {}
    if d.facility_kind:
        fds = facility_datasets(session, d.facility_kind)
        if not fds:
            result.skipped_reason = f"no {d.facility_kind} facilities loaded"
            return result
        fac_src = sources_by_state(session, fds, "facility")
        states = sorted(fac_src)
    if d.kind in ("per_10k", "density"):
        inputs.append(pop_ds)
    if d.kind == "settlements_beyond":
        sds = session.execute(text("SELECT DISTINCT dataset_id FROM settlement")).scalars().all()
        if not sds:
            result.skipped_reason = "no settlements loaded"
            return result
        settlement_sets = list(session.scalars(select(Dataset).where(Dataset.id.in_(sds))))
        set_src = sources_by_state(session, settlement_sets, "settlement")
        states = sorted(set(states) & set(set_src))
    used = {ds.id: ds for sid, ds in [*fac_src.items(), *set_src.items()] if sid in states}
    inputs += list(used.values())
    if (d.facility_kind or d.kind == "settlements_beyond") and not states:
        result.skipped_reason = "no state is covered by every input this indicator needs"
        return result

    out_ds = derived_dataset(
        session,
        key=f"derived-{d.indicator}",
        title=f"Derived: {d.indicator}",
        method=session.scalar(text("SELECT method FROM indicator WHERE id = :i"), {"i": ind})
        or d.indicator,
        inputs=inputs,
    )
    session.execute(text("DELETE FROM observation WHERE dataset_id = :ds"), {"ds": out_ds.id})
    if fac_src or set_src:
        names = dict(
            session.execute(
                text("SELECT id, name FROM admin_area WHERE id = ANY(:i)"), {"i": states}
            ).all()
        )
        out_ds.extra = {
            **(out_ds.extra or {}),
            "coverage_state_ids": states,
            "sources_by_state": {
                names[sid]: {
                    k: v.key
                    for k, v in (
                        ("facilities", fac_src.get(sid)),
                        ("settlements", set_src.get(sid)),
                    )
                    if v
                }
                for sid in states
            },
        }

    for level in d.levels:
        params = {"ind": ind, "ds": out_ds.id, "period": period, "level": level}
        state_filter = ""
        if d.facility_kind or d.kind == "settlements_beyond":
            state_filter = f"AND {_area_scope_sql(level)} = ANY(:states)"
            params["states"] = states
        params["fsrc_states"] = [sid for sid in states if sid in fac_src]
        params["fsrc_ds"] = [fac_src[sid].id for sid in params["fsrc_states"]]
        params["ssrc_states"] = [sid for sid in states if sid in set_src]
        params["ssrc_ds"] = [set_src[sid].id for sid in params["ssrc_states"]]
        if d.kind == "density":
            sql = f"""
                INSERT INTO observation (indicator_id, geo_level, geo_id, period, value,
                    value_type, verification_status, dataset_id, source_reference)
                SELECT :ind, a.level, a.id, :period, p.value / a.area_km2, 'derived',
                       'unverified', :ds, 'modelled population ÷ area_km2'
                FROM admin_area a
                JOIN observation p ON p.geo_level = :level AND p.geo_id = a.id
                 AND p.indicator_id = (SELECT id FROM indicator WHERE code = '{POPULATION}')
                WHERE a.level = :level AND a.active AND a.area_km2 > 0
            """
        elif d.kind == "per_10k":
            col = _area_facility_column(level)
            params["kind"] = d.facility_kind
            sql = f"""
                INSERT INTO observation (indicator_id, geo_level, geo_id, period, value,
                    value_type, verification_status, dataset_id, source_reference, note)
                SELECT :ind, a.level, a.id, :period,
                       10000.0 * count(f.id) / p.value, 'derived', 'unverified', :ds,
                       count(f.id) || ' facilities ÷ modelled population ' || round(p.value),
                       'Population is a modelled estimate; facilities from loaded datasets only.'
                FROM admin_area a
                JOIN observation p ON p.geo_level = :level AND p.geo_id = a.id
                 AND p.indicator_id = (SELECT id FROM indicator WHERE code = '{POPULATION}')
                LEFT JOIN facility f ON f.{col} = a.id AND f.kind = :kind AND {FACILITY_SOURCE}
                 AND NOT {NON_FUNCTIONAL} {_subtype_filter(d)}
                WHERE a.level = :level AND a.active AND p.value > 0 {state_filter}
                GROUP BY a.id, p.value
            """
        elif d.kind == "nearest_km":
            params["kind"] = d.facility_kind
            sql = f"""
                INSERT INTO observation (indicator_id, geo_level, geo_id, period, value,
                    value_type, verification_status, dataset_id, source_reference)
                SELECT :ind, a.level, a.id, :period, n.km, 'derived', 'unverified', :ds,
                       'nearest: ' || coalesce(n.name, 'unnamed') || ' (facility ' || n.id || ')'
                FROM admin_area a
                CROSS JOIN LATERAL (
                    SELECT f.id, f.name,
                           ST_Distance(f.geom::geography, ST_PointOnSurface(a.geom)::geography) / 1000.0 AS km
                    FROM facility f
                    WHERE f.kind = :kind AND {FACILITY_SOURCE} AND NOT {NON_FUNCTIONAL} {_subtype_filter(d)}
                    ORDER BY f.geom <-> ST_PointOnSurface(a.geom)
                    LIMIT 1
                ) n
                WHERE a.level = :level AND a.active {state_filter}
            """
        elif d.kind == "settlements_beyond":
            params["kind"] = d.facility_kind
            params["m"] = d.threshold_km * 1000
            sql = f"""
                INSERT INTO observation (indicator_id, geo_level, geo_id, period, value,
                    value_type, verification_status, dataset_id, source_reference)
                SELECT :ind, a.level, a.id, :period,
                       100.0 * count(*) FILTER (WHERE n.m > :m) / count(*), 'derived',
                       'unverified', :ds, count(*) || ' settlements'
                FROM admin_area a
                JOIN settlement s ON s.ward_id = a.id AND {SETTLEMENT_SOURCE}
                CROSS JOIN LATERAL (
                    SELECT ST_Distance(f.geom::geography, s.point::geography) AS m
                    FROM facility f
                    WHERE f.kind = :kind AND {FACILITY_SOURCE} AND NOT {NON_FUNCTIONAL} {_subtype_filter(d)}
                    ORDER BY f.geom <-> s.point LIMIT 1
                ) n
                WHERE a.level = :level AND a.active {state_filter}
                GROUP BY a.id
            """
        else:
            raise ValueError(d.kind)
        result.stored[level] = session.execute(text(sql), params).rowcount
    out_ds.status = "loaded"
    out_ds.record_count = sum(result.stored.values())
    out_ds.reference_period = period
    session.flush()
    return result


def run_all(session: Session, only: str | None = None) -> list[DeriveResult]:
    out = []
    for d in DERIVATIONS:
        if only and d.indicator != only:
            continue
        out.append(run_derivation(session, d))
    return out
