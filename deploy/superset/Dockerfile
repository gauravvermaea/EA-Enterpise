# Apache Superset, used as is, plus the drivers it needs here:
#   psycopg2 (PostgreSQL), Authlib (sign-in through Keycloak), redis (cache in Valkey).
# Recent Superset images ship without database drivers, so they are added on top.
ARG SUPERSET_IMAGE=apache/superset:4.1.2
FROM ${SUPERSET_IMAGE}
USER root
RUN pip install --no-cache-dir "psycopg2-binary>=2.9,<3" "Authlib>=1.3,<2" "redis>=5,<6"
USER superset
