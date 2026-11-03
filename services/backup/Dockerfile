# EA Explorer backup image (ours): PostgreSQL client tools on a schedule (busybox crond)
ARG POSTGRES_IMAGE=postgres:17-alpine
FROM ${POSTGRES_IMAGE}
COPY *.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
