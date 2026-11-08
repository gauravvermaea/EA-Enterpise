# EA Explorer operations helper (phase 10, D183): restarts the system when a Super Admin asks from the administration
# console. Reaches the Docker engine through its socket; only on the internal network, no published port; every request
# needs EAX_OPS_TOKEN. Port 8091 answers only interactive terminals, opened with a one-time ticket (D214). Accepts only: status, restart (all or one service), switch an optional service on or off
# (writing the config file in the work folder, a dated copy first), list and restore copies of the config file.
FROM docker:27.3-cli
RUN apk add --no-cache python3
WORKDIR /app
COPY ops.py /app/ops.py
COPY console.py /app/console.py
USER root
EXPOSE 8090 8091
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8090/health').status==200 else 1)"
CMD ["python3", "-u", "/app/ops.py"]
