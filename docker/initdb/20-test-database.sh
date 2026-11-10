#!/bin/sh
# Runs once, when the database volume is first created. Adds the separate database that
# the automated tests use (they wipe it on every run, so it must not be the main one).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE DATABASE connectly_test OWNER connectly;
\connect connectly_test
CREATE EXTENSION IF NOT EXISTS postgis;
SQL
