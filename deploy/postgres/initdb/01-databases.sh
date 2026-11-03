#!/bin/sh
# Runs once, when the PostgreSQL data folder is first created.
# Creates the four databases and their logins. Each product gets its own login and cannot read
# the others' databases.
#   eaexplorer : ours (owner eax_app; eax_report is a read-only login for reports, granted on
#                the rpt schema by our migrations)
#   keycloak, superset, mayan : created empty here; each product creates its own tables
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v eax_db="${EAX_DB_NAME:-eaexplorer}" \
  -v eax_pw="$EAX_DB_PASSWORD" \
  -v rpt_pw="$EAX_DB_REPORT_PASSWORD" \
  -v kc_pw="$EAX_KEYCLOAK_DB_PASSWORD" \
  -v ss_pw="$EAX_SUPERSET_DB_PASSWORD" \
  -v my_pw="$EAX_MAYAN_DB_PASSWORD" <<'SQL'
CREATE ROLE eax_app    LOGIN PASSWORD :'eax_pw';
CREATE ROLE eax_report LOGIN PASSWORD :'rpt_pw';
CREATE ROLE keycloak   LOGIN PASSWORD :'kc_pw';
CREATE ROLE superset   LOGIN PASSWORD :'ss_pw';
CREATE ROLE mayan      LOGIN PASSWORD :'my_pw';

CREATE DATABASE :"eax_db" OWNER eax_app;
CREATE DATABASE keycloak  OWNER keycloak;
CREATE DATABASE superset  OWNER superset;
CREATE DATABASE mayan     OWNER mayan;

REVOKE ALL ON DATABASE :"eax_db" FROM PUBLIC;
REVOKE ALL ON DATABASE keycloak  FROM PUBLIC;
REVOKE ALL ON DATABASE superset  FROM PUBLIC;
REVOKE ALL ON DATABASE mayan     FROM PUBLIC;
GRANT CONNECT ON DATABASE :"eax_db" TO eax_report;
SQL

# Extensions our repository database needs (created by the superuser, used by eax_app)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${EAX_DB_NAME:-eaexplorer}" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL

echo "EA Explorer: databases eaexplorer, keycloak, superset and mayan created."
