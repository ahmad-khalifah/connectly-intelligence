"""Post-load consistency checks declared in a manifest's `checks` list.

ancestor_code: compare a code column in the loaded file with the area it actually falls
inside. Example: a ward row says stat_cd = "AD"; the ward must lie in the state whose
aliases include "NG-AD". Mismatches are reported, not silently corrected.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ingest.manifest import Manifest

ANCESTOR_SQL = {
    ("ward", "lga"): "a.parent_id",
    ("ward", "state"): "(SELECT parent_id FROM admin_area WHERE id = a.parent_id)",
    ("lga", "state"): "a.parent_id",
}


def run_checks(session: Session, manifest: Manifest, dataset_id: int) -> list[str]:
    warnings: list[str] = []
    for check in manifest.checks or []:
        if check.get("type") != "ancestor_code":
            warnings.append(f"unknown check type {check.get('type')!r} ignored")
            continue
        warnings.extend(_ancestor_code(session, manifest.level, dataset_id, check))
    return warnings


def _ancestor_code(session: Session, level: str, dataset_id: int, check: dict) -> list[str]:
    anc_level = check["ancestor_level"]
    expr = ANCESTOR_SQL.get((level, anc_level))
    if expr is None:
        return [f"ancestor_code check: unsupported {level} → {anc_level}"]
    template = check.get("alias_template", "{value}")
    prefix, _, suffix = template.partition("{value}")
    code_map = {str(k).upper(): str(v).upper() for k, v in (check.get("code_map") or {}).items()}
    rows = session.execute(
        text(
            f"""
            SELECT a.name, a.attributes->>:attr AS code, anc.name AS anc_name,
                   EXISTS (SELECT 1 FROM place_alias pa
                           WHERE pa.admin_area_id = anc.id
                             AND upper(pa.alias) = upper(:prefix || COALESCE(
                                   (CAST(:code_map AS jsonb))->>upper(a.attributes->>:attr),
                                   a.attributes->>:attr) || :suffix))
                     AS matches
            FROM admin_area a
            LEFT JOIN admin_area anc ON anc.id = {expr}
            WHERE a.dataset_id = :ds AND a.active
            """
        ),
        {
            "attr": check["attribute"],
            "ds": dataset_id,
            "prefix": prefix,
            "suffix": suffix,
            "code_map": json.dumps(code_map),
        },
    ).all()
    bad = [r for r in rows if not r.matches]
    total = len(rows)
    if not bad:
        return [
            f"check passed: all {total} {level}s have {check['attribute']} matching the "
            f"{anc_level} they lie in"
        ]
    sample = ", ".join(f"{r.name} ({r.code}) in {r.anc_name or 'none'}" for r in bad[:8])
    return [
        f"check: {len(bad)} of {total} {level}s have {check['attribute']} that does not match "
        f"the {anc_level} they lie in: {sample}"
    ]
