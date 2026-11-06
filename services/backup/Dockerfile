# EA Explorer backup image (ours): PostgreSQL client tools; the operations helper runs backup.sh and restore.sh in it (D216)
ARG POSTGRES_IMAGE=postgres:17-alpine
FROM ${POSTGRES_IMAGE}
COPY *.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
