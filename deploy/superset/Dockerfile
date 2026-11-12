# Apache Superset, used as is, plus the drivers it needs here:
#   psycopg2 (PostgreSQL) and Authlib (sign-in through Keycloak). Caches live in PostgreSQL.
# Recent Superset images ship without database drivers, so they are added on top.
ARG SUPERSET_IMAGE=apache/superset:4.1.2
FROM ${SUPERSET_IMAGE}
USER root
# the Debian packages' own fixes (OpenSSL, GnuTLS, MariaDB client, perl…: R2.24)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "psycopg2-binary>=2.9,<3" "Authlib>=1.3,<2" \
 # Python packages inside Superset with critical vulnerabilities fixed in newer releases (R2.24, the full self-test 12 Nov 2026)
 && pip install --no-cache-dir --upgrade "Brotli>=1.2.1" "PyJWT>=2.14.0,<3" "certifi>=2026.10.18"
USER superset
