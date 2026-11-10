"""Shared rules for comparing the models with the live database schema."""

from geoalchemy2 import alembic_helpers


def include_object(obj, name, type_, reflected, compare_to):
    """Only compare objects this application owns.

    PostGIS images install extension tables (spatial_ref_sys, topology, the tiger
    geocoder's addr, edges, ...). They exist in the database but not in our models,
    and must never be reported as drift or dropped by autogenerate.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)
