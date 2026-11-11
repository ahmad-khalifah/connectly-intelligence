"""Load administrative boundaries into `admin_area` with full provenance.

Pipeline: read file → check CRS and extent → map fields → repair geometry → reject bad
rows → (optionally) keep only areas inside one state → upsert with stable IDs →
activate → assign parents by spatial overlap → run post-load checks.

Every run is recorded in `ingest_run`, including rejected rows and warnings.
"""

from __future__ import annotations

import json
from pathlib import Path

import shapely
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connectly.ingest import observations as obs
from connectly.ingest.checks import run_checks
from connectly.ingest.common import (  # noqa: F401 - re-exported for callers
    FileNotProvidedError,
    LoadError,
    LoadReport,
    clean_code,
    clean_name,
    finish_run,
    json_safe,
    manifest_fingerprint,
    pick_column,
    read_vector,
    record_failure,
    repair_polygonal,
    resolve_file,
    skip_if_loaded,
    start_run,
    upsert_dataset,
)
from connectly.ingest.fetch import describe_local_file
from connectly.ingest.manifest import Manifest
from connectly.models import PARENT_LEVEL, AdminArea, PlaceAlias

CHILD_LEVEL = {parent: child for child, parent in PARENT_LEVEL.items()}
LOW_OVERLAP = 0.95


def prepare_features(
    path: Path,
    manifest: Manifest,
    within: BaseGeometry | None = None,
) -> tuple[list[dict], LoadReport]:
    report = LoadReport(dataset_key=manifest.key, status="running")
    gdf = read_vector(path, manifest, report)

    columns = [c for c in gdf.columns if c != gdf.geometry.name]
    name_col = pick_column(columns, manifest.field_candidates("name"), "name")
    code_col = pick_column(columns, manifest.field_candidates("code"), "code")
    alias_cols = [c for c in manifest.field_candidates("alias_codes") if c in columns]

    within_prepared = prep(within) if within is not None else None
    rows: list[dict] = []
    rejected: list[str] = []
    repaired_count = 0
    for idx, rec in gdf.iterrows():
        name = clean_name(rec[name_col])
        code = clean_code(rec[code_col])
        if not name or not code:
            rejected.append(f"row {idx}: missing name or code")
            continue
        geom, repaired = repair_polygonal(rec.geometry)
        if geom is None:
            rejected.append(f"row {idx} ({name}): empty or non-polygonal geometry")
            continue
        repaired_count += int(repaired)
        if within_prepared is not None and not within_prepared.contains(
            geom.representative_point()
        ):
            report.rows_out_of_scope += 1
            continue
        attrs = {c: json_safe(rec[c]) for c in columns}
        aliases = [str(rec[c]).strip() for c in alias_cols if clean_name(rec[c])]
        aliases += (manifest.name_aliases or {}).get(name, [])
        if manifest.rename and name in manifest.rename:
            aliases.append(name)
            name = manifest.rename[name]
        rows.append(
            {
                "name": name,
                "source_name": str(rec[name_col]),
                "source_code": code,
                "geom": geom,
                "attributes": attrs,
                "aliases": aliases,
            }
        )

    codes = [r["source_code"] for r in rows]
    dupes = sorted({c for c in codes if codes.count(c) > 1})
    if dupes:
        raise LoadError(f"duplicate codes in column {code_col!r}: {dupes[:10]}")
    if repaired_count:
        report.warnings.append(f"repaired {repaired_count} invalid geometries with make_valid")
    if rejected:
        report.warnings.append(f"rejected {len(rejected)} rows: " + "; ".join(rejected[:10]))
    report.rows_rejected = len(rejected)
    return rows, report


# --------------------------------------------------------------------------- hierarchy


def find_active_area(session: Session, level: str, name: str) -> AdminArea:
    """Find an active area by name or alias, case-insensitively."""
    q = text(
        """
        SELECT a.id FROM admin_area a
        WHERE a.level = :level AND a.active
          AND (lower(a.name) = lower(:name)
               OR EXISTS (SELECT 1 FROM place_alias p
                          WHERE p.admin_area_id = a.id AND lower(p.alias) = lower(:name)))
        """
    )
    ids = session.execute(q, {"level": level, "name": name}).scalars().all()
    if len(ids) == 1:
        return session.get(AdminArea, ids[0])
    names = (
        session.execute(
            text("SELECT name FROM admin_area WHERE level = :level AND active ORDER BY name"),
            {"level": level},
        )
        .scalars()
        .all()
    )
    if not ids:
        raise LoadError(f"no active {level} named {name!r}. Available: {names}")
    raise LoadError(f"{name!r} matches {len(ids)} active {level}s; be more specific")


def area_shape(session: Session, area_id: int) -> BaseGeometry:
    wkb = session.execute(
        text("SELECT ST_AsBinary(geom) FROM admin_area WHERE id = :id"), {"id": area_id}
    ).scalar_one()
    return shapely.from_wkb(bytes(wkb))


def boundary_coverage(
    session: Session, manifest: Manifest, dataset_id: int, within_sid: int | None
) -> tuple[list[int], str]:
    """States whose areas this boundary dataset provides (see ingest/coverage.py)."""
    from connectly.ingest.coverage import (
        METHOD_DECLARED,
        METHOD_OBSERVED,
        METHOD_WITHIN,
        resolve_state_names,
    )

    if within_sid is not None:
        return [within_sid], METHOD_WITHIN
    if manifest.coverage_states:
        return resolve_state_names(session, manifest.coverage_states), METHOD_DECLARED
    observed = (
        session.execute(
            text(
                """
            SELECT DISTINCT s.id FROM admin_area a
            JOIN admin_area s ON s.level = 'state' AND s.active
             AND ST_Contains(s.geom, ST_PointOnSurface(a.geom))
            WHERE a.dataset_id = :ds ORDER BY s.id
            """
            ),
            {"ds": dataset_id},
        )
        .scalars()
        .all()
    )
    return list(observed), METHOD_OBSERVED


def activate_dataset(
    session: Session, dataset_id: int, level: str, state_ids: list[int] | None = None
) -> None:
    """Make a dataset the active source for `level`.

    For LGAs and wards, activation is limited to `state_ids`: a ward file that covers some
    states replaces wards only there, and every other state keeps the wards it had.
    Countries and states are always replaced as a whole.
    """
    if level in ("country", "state") or state_ids is None:
        session.execute(
            text("UPDATE admin_area SET active = (dataset_id = :ds) WHERE level = :level"),
            {"ds": dataset_id, "level": level},
        )
    else:
        session.execute(
            text(
                """
                WITH placed AS (
                  SELECT a.id, s.id AS state_id
                  FROM admin_area a
                  LEFT JOIN admin_area s ON s.level = 'state' AND s.active
                   AND ST_Contains(s.geom, ST_PointOnSurface(a.geom))
                  WHERE a.level = :level
                )
                UPDATE admin_area a
                   SET active = (a.dataset_id = :ds AND p.state_id = ANY(:states))
                  FROM placed p
                 WHERE a.id = p.id
                   AND (a.dataset_id = :ds OR p.state_id = ANY(:states))
                """
            ),
            {"ds": dataset_id, "level": level, "states": state_ids},
        )
    # A dataset is superseded only once none of its areas is active anywhere.
    session.execute(
        text(
            """
            UPDATE dataset d SET status = 'superseded'
            WHERE d.id <> :ds AND d.status = 'loaded'
              AND EXISTS (SELECT 1 FROM admin_area a WHERE a.dataset_id = d.id AND a.level = :level)
              AND NOT EXISTS (SELECT 1 FROM admin_area a
                              WHERE a.dataset_id = d.id AND a.level = :level AND a.active)
            """
        ),
        {"ds": dataset_id, "level": level},
    )


def assign_parents(session: Session, level: str) -> int:
    """Link each active area to the active parent it overlaps most. Returns rows linked."""
    parent_level = PARENT_LEVEL.get(level)
    if parent_level is None:
        session.execute(
            text(
                "UPDATE admin_area SET parent_id = NULL, parent_overlap = NULL, "
                "parent_method = 'none' WHERE level = :level AND active"
            ),
            {"level": level},
        )
        return 0
    linked = session.execute(
        text(
            """
            WITH best AS (
              SELECT DISTINCT ON (c.id) c.id AS cid, p.id AS pid,
                     ST_Area(ST_Intersection(c.geom, p.geom)) / NULLIF(ST_Area(c.geom), 0)
                       AS ratio
              FROM admin_area c
              JOIN admin_area p
                ON p.level = :plevel AND p.active
               AND c.geom && p.geom AND ST_Intersects(c.geom, p.geom)
              WHERE c.level = :level AND c.active
              ORDER BY c.id, ratio DESC NULLS LAST
            )
            UPDATE admin_area c
               SET parent_id = best.pid,
                   parent_overlap = LEAST(1.0, best.ratio),
                   parent_method = 'spatial_overlap'
              FROM best
             WHERE c.id = best.cid
            """
        ),
        {"level": level, "plevel": parent_level},
    ).rowcount
    session.execute(
        text(
            """
            UPDATE admin_area c
               SET parent_id = NULL, parent_overlap = NULL, parent_method = 'none'
             WHERE c.level = :level AND c.active
               AND NOT EXISTS (SELECT 1 FROM admin_area p
                               WHERE p.level = :plevel AND p.active
                                 AND c.geom && p.geom AND ST_Intersects(c.geom, p.geom))
            """
        ),
        {"level": level, "plevel": parent_level},
    )
    return linked


def hierarchy_warnings(session: Session, level: str) -> list[str]:
    out: list[str] = []
    if level in PARENT_LEVEL:
        low = session.execute(
            text(
                """
                SELECT c.name, p.name, round(c.parent_overlap::numeric, 3)
                FROM admin_area c LEFT JOIN admin_area p ON p.id = c.parent_id
                WHERE c.level = :level AND c.active
                  AND (c.parent_id IS NULL OR c.parent_overlap < :thr)
                ORDER BY c.parent_overlap NULLS FIRST
                """
            ),
            {"level": level, "thr": LOW_OVERLAP},
        ).all()
        if low:
            sample = ", ".join(f"{c} → {p or 'none'} ({o})" for c, p, o in low[:10])
            out.append(
                f"{len(low)} {level} areas have no parent or lie less than "
                f"{int(LOW_OVERLAP * 100)}% inside their parent: {sample}"
            )
    dupes = session.execute(
        text(
            """
            SELECT name, count(*) FROM admin_area
            WHERE level = :level AND active
            GROUP BY parent_id, name HAVING count(*) > 1
            """
        ),
        {"level": level},
    ).all()
    if dupes:
        out.append(
            f"duplicate {level} names under the same parent: "
            + ", ".join(f"{n} ×{c}" for n, c in dupes[:10])
        )
    return out


# --------------------------------------------------------------------------- loading

UPSERT_SQL = text(
    """
    INSERT INTO admin_area (level, name, source_name, source_code, dataset_id, active,
                            geom, attributes)
    VALUES (:level, :name, :source_name, :source_code, :dataset_id, false,
            ST_Multi(ST_SetSRID(ST_GeomFromWKB(:wkb), 4326)), CAST(:attributes AS jsonb))
    ON CONFLICT ON CONSTRAINT uq_admin_area_dataset_code DO UPDATE
       SET name = EXCLUDED.name,
           source_name = EXCLUDED.source_name,
           geom = EXCLUDED.geom,
           attributes = EXCLUDED.attributes,
           updated_at = now()
    RETURNING id
    """
)


def load_boundaries(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    within_state: str | None = None,
    activate: str = "auto",
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
    if activate not in ("auto", "yes", "no"):
        raise ValueError("activate must be 'auto', 'yes' or 'no'")
    level = manifest.level
    path = resolve_file(manifest, file, raw_dir)
    retrieved = describe_local_file(path, url=manifest.download.url)
    params = {
        "file": path.name,
        "within_state": within_state,
        "activate": activate,
        "manifest": manifest_fingerprint(manifest),
    }

    ds = upsert_dataset(session, manifest, retrieved)
    skipped = skip_if_loaded(session, ds, retrieved.sha256, params, force)
    if skipped:
        return LoadReport(
            dataset_key=manifest.key,
            status="skipped",
            run_id=skipped.id,
            warnings=skipped.warnings,
            active=_is_active(session, ds.id, level),
        )
    run = start_run(session, ds, params)

    within_geom = None
    within_sid = None
    if within_state:
        state = find_active_area(session, "state", within_state)
        within_sid = state.id
        within_geom = area_shape(session, state.id)

    rows, report = prepare_features(path, manifest, within=within_geom)
    if not rows:
        raise LoadError(
            f"no usable features after filtering (read {report.rows_read}, "
            f"rejected {report.rows_rejected}, outside scope {report.rows_out_of_scope})"
        )

    code_to_id: dict[str, int] = {}
    for r in rows:
        new_id = session.execute(
            UPSERT_SQL,
            {
                "level": level,
                "name": r["name"],
                "source_name": r["source_name"],
                "source_code": r["source_code"],
                "dataset_id": ds.id,
                "wkb": shapely.to_wkb(r["geom"]),
                "attributes": json.dumps(r["attributes"]),
            },
        ).scalar_one()
        code_to_id[r["source_code"]] = new_id
        for alias in r["aliases"]:
            exists = session.scalar(
                select(PlaceAlias.id).where(
                    PlaceAlias.admin_area_id == new_id, PlaceAlias.alias == alias
                )
            )
            if not exists:
                session.add(PlaceAlias(admin_area_id=new_id, alias=alias, source=manifest.key))
    session.flush()

    if within_state is None:
        # A full load replaces the dataset: remove areas no longer in the file.
        removed = session.execute(
            text(
                "DELETE FROM admin_area WHERE dataset_id = :ds AND level = :level "
                "AND NOT (id = ANY(:ids))"
            ),
            {"ds": ds.id, "level": level, "ids": list(code_to_id.values())},
        ).rowcount
        if removed:
            report.warnings.append(f"removed {removed} areas no longer present in the file")

    session.execute(
        text(
            "UPDATE admin_area SET area_km2 = ST_Area(geom::geography) / 1e6 WHERE dataset_id = :ds"
        ),
        {"ds": ds.id},
    )

    others_active = session.scalar(
        text(
            "SELECT count(*) FROM admin_area WHERE level = :level AND active AND dataset_id <> :ds"
        ),
        {"level": level, "ds": ds.id},
    )
    should_activate = activate == "yes" or (
        activate == "auto" and (others_active == 0 or _is_active(session, ds.id, level))
    )
    if should_activate:
        covered, method = boundary_coverage(session, manifest, ds.id, within_sid)
        ds.extra = {**(ds.extra or {}), "coverage_state_ids": covered, "coverage_method": method}
        activate_dataset(session, ds.id, level, covered)
        assign_parents(session, level)
        child = CHILD_LEVEL.get(level)
        if child:
            assign_parents(session, child)
        if level in ("lga", "ward"):
            # Facilities and settlements must point at the areas now active.
            from connectly.ingest.points import link_to_admin

            for table in ("facility", "settlement"):
                link_to_admin(session, table)
            n_states = session.scalar(
                text("SELECT count(*) FROM admin_area WHERE level = 'state' AND active")
            )
            if len(covered) < n_states:
                report.warnings.append(
                    f"activated in {len(covered)} of {n_states} states ({method}); "
                    "other states keep their existing areas"
                )
        report.warnings.extend(hierarchy_warnings(session, level))
        report.warnings.extend(run_checks(session, manifest, ds.id))
    else:
        report.warnings.append(
            f"loaded but NOT active: another dataset is active for level {level!r}. "
            f"Re-run with --activate yes to switch."
        )

    if manifest.observations:
        attrs_by_id = {code_to_id[r["source_code"]]: r["attributes"] for r in rows}
        stored = obs.store_attribute_observations(session, manifest, ds, level, attrs_by_id)
        report.warnings.extend(stored.warnings)

    total = session.scalar(
        text("SELECT count(*) FROM admin_area WHERE dataset_id = :ds"), {"ds": ds.id}
    )
    if manifest.expected_count and within_state is None and total != manifest.expected_count:
        report.warnings.append(f"expected {manifest.expected_count} areas, found {total}")

    report.rows_loaded = len(rows)
    report.active = should_activate
    status = "loaded" if should_activate or ds.status != "superseded" else ds.status
    finish_run(session, run, ds, report, retrieved.sha256, params, total, status=status)
    return report


def _is_active(session: Session, dataset_id: int, level: str) -> bool:
    return bool(
        session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM admin_area WHERE dataset_id = :ds "
                "AND level = :level AND active)"
            ),
            {"ds": dataset_id, "level": level},
        )
    )
