# EA Explorer backup image (ours): PostgreSQL client tools; the operations helper runs backup.sh and restore.sh in it (D216)
# a current patch release (17-alpine stayed as first pulled on a laptop: its Go standard library had a critical
# vulnerability, R2.24); then the Alpine packages' own fixes
ARG POSTGRES_IMAGE=postgres:17.11-alpine
FROM ${POSTGRES_IMAGE}
RUN apk upgrade --no-cache \
 # gosu (the image's tool to start the server as postgres) carries a Go standard library with a critical vulnerability
 # and this image never starts a server: it only runs pg_dump, pg_restore and psql (R2.24, the full self-test 12 Nov 2026)
 && rm -f /usr/local/bin/gosu /usr/local/bin/su-exec
COPY *.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
