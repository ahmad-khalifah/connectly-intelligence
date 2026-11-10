"""Import directory records from a YAML file (for curated batches entered offline).

Format (see docs/directory.md):

    organisations:
      - name: Example Health Ltd
        org_type: startup
        headquarters: Yola
        headquarters_country: NG
        headquarters_state: Adamawa
        source_description: Company website, retrieved 2026-11-10
        source_url: https://example.org/about
        solutions:
          - name: Example Clinic App
            status: draft            # draft (default) or published
            sector: health
            ...                      # any SolutionIn field
            coverage:
              - {state: Adamawa}
              - {state: Adamawa, lga: Yola North, kind: expansion_interest}

Records are matched by organisation name and solution name, so re-importing a file updates
them. Every record is validated before anything is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from connectly.models import Organisation, Solution
from connectly.services import audit
from connectly.services.directory import (
    AUDIT_ORG_FIELDS,
    DirectoryError,
    OrganisationIn,
    SolutionIn,
    apply_organisation,
    apply_solution,
    publish,
    snapshot_solution,
)


@dataclass
class ImportReport:
    organisations_created: int = 0
    organisations_updated: int = 0
    solutions_created: int = 0
    solutions_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _area_id(session: Session, ref: dict) -> int:
    state = ref.get("state")
    if not state:
        raise DirectoryError(f"coverage entry needs a state: {ref}")
    sid = session.scalar(
        text(
            "SELECT a.id FROM admin_area a WHERE a.level = 'state' AND a.active AND "
            "(lower(a.name) = lower(:n) OR EXISTS (SELECT 1 FROM place_alias p "
            "WHERE p.admin_area_id = a.id AND lower(p.alias) = lower(:n)))"
        ),
        {"n": state},
    )
    if sid is None:
        raise DirectoryError(f"unknown state {state!r}")
    for level in ("lga", "ward"):
        name = ref.get(level)
        if not name:
            break
        found = session.scalars(
            text(
                "SELECT id FROM admin_area WHERE level = :l AND parent_id = :p AND active "
                "AND lower(name) = lower(:n)"
            ),
            {"l": level, "p": sid, "n": name},
        ).all()
        if len(found) != 1:
            raise DirectoryError(f"{level} {name!r} not found (or ambiguous) under {state}")
        sid = found[0]
    return sid


def _parse(session: Session, data: dict) -> list[tuple[OrganisationIn, dict, list]]:
    if not isinstance(data, dict) or not isinstance(data.get("organisations"), list):
        raise DirectoryError("the file must contain a list under 'organisations'")
    parsed = []
    for i, o in enumerate(data["organisations"]):
        o = dict(o)
        where = f"organisations[{i}] ({o.get('name', '?')})"
        sols = o.pop("solutions", []) or []
        meta = {"status": o.pop("status", "active")}
        hq_state = o.pop("headquarters_state", None)
        try:
            if hq_state:
                o["headquarters_state_id"] = _area_id(session, {"state": hq_state})
            org_in = OrganisationIn(**o)
        except (ValidationError, DirectoryError) as e:
            raise DirectoryError(f"{where}: {e}") from None
        sol_items = []
        for j, s in enumerate(sols):
            s = dict(s)
            swhere = f"{where}.solutions[{j}] ({s.get('name', '?')})"
            status = s.pop("status", "draft")
            if status not in ("draft", "published"):
                raise DirectoryError(f"{swhere}: status must be draft or published")
            try:
                s["coverage"] = [
                    {"area_id": _area_id(session, c), "kind": c.get("kind", "operating")}
                    for c in s.get("coverage", []) or []
                ]
                sol_items.append((SolutionIn(**s), status))
            except (ValidationError, DirectoryError) as e:
                raise DirectoryError(f"{swhere}: {e}") from None
        parsed.append((org_in, meta, sol_items))
    return parsed


def import_directory(session: Session, path: Path, actor: str = "cli") -> ImportReport:
    report = ImportReport()
    parsed = _parse(session, yaml.safe_load(path.read_text(encoding="utf-8")))
    for org_in, meta, sol_items in parsed:
        org = session.scalar(
            select(Organisation).where(func.lower(Organisation.name) == org_in.name.lower())
        )
        created = org is None
        if created:
            org = Organisation(status=meta["status"])
            session.add(org)
        before = {} if created else audit.snapshot(org, AUDIT_ORG_FIELDS)
        apply_organisation(session, org, org_in)
        session.flush()
        after = audit.snapshot(org, AUDIT_ORG_FIELDS)
        audit.record(
            session,
            actor,
            "import",
            "organisation",
            org.id,
            str(path.name),
            {"after": after} if created else audit.diff(before, after),
        )
        report.organisations_created += created
        report.organisations_updated += not created
        for sol_in, status in sol_items:
            sol = session.scalar(
                select(Solution).where(
                    Solution.organisation_id == org.id,
                    func.lower(Solution.name) == sol_in.name.lower(),
                )
            )
            s_created = sol is None
            if s_created:
                sol = Solution(organisation_id=org.id, status="draft")
                session.add(sol)
            s_before = {} if s_created else snapshot_solution(session, sol)
            apply_solution(session, sol, sol_in)
            if status == "published" and sol.status != "published":
                if org.status != "active":
                    raise DirectoryError(
                        f"{org.name}: organisation status is {org.status}; cannot publish"
                    )
                publish(sol)
            s_after = snapshot_solution(session, sol)
            audit.record(
                session,
                actor,
                "import",
                "solution",
                sol.id,
                str(path.name),
                {"after": s_after} if s_created else audit.diff(s_before, s_after),
            )
            report.solutions_created += s_created
            report.solutions_updated += not s_created
    return report
