#!/bin/sh
# EA Explorer api container.
#   EAX_ROLE=api (default): wait for the database, apply migrations, the job-queue schema and the core seed
#                           (what everyone needs to sign in; the rest loads after the API has started, D255),
#                           (one server at a time when there are several, D249), then run the web API (gunicorn),
#                           the job runner, the change log shipper (on one server only) and the MCP
#                           server (uvicorn, port 8001) side by side; the change log and the MCP server only when
#                           switched on (EAX_SERVICE_CHANGE_LOG, EAX_SERVICE_MCP; on by default, D191).
#   any other command:      run it as given (the setup service uses: python -m eax.setup).
set -eu
cd /app

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python -m eax.wait_for_db
# several API and job servers may start together (D249): the upgrade and the seed run on one at a time
echo "EA Explorer: applying database migrations"
python -m eax.startup serial -- sh -c "alembic upgrade head && python -m eax.jobs_schema && python -m eax.seed"

echo "EA Explorer: starting the API and the job runner"
gunicorn --bind 0.0.0.0:8000 --workers "${EAX_API_WORKERS:-2}" --access-logfile - "eax.wsgi:app" &
API_PID=$!
procrastinate --app=eax.jobs.app worker --concurrency "${EAX_JOB_CONCURRENCY:-2}" &
JOBS_PID=$!
# the change log (phase 9, D180): ships finished changes to its own database every few seconds; it logs and retries
# on errors and never stops the API. Switched off: no new entries (D191)
if python -m eax.services is-on change_log; then
  python -m eax.startup single change_log -- python -m eax.change_log &   # on one server only (D249)
else
  echo "EA Explorer: the change log is switched off (EAX_SERVICE_CHANGE_LOG=off): no new entries"
fi
# the second tier of the start-up (D255): the sample and laptop test models, the demo estate and the first data quality
# measurement, in the background, one step at a time, so the API is healthy at once and people can sign in; it logs each
# step, records how far it has got (core.startup_parts, shown to everyone) and never stops the container
# (eax/seed/later.py). With several servers one runs it.
python -m eax.startup once later -- python -m eax.seed.later &
MCP_PID=""
if python -m eax.services is-on mcp; then
  echo "EA Explorer: starting the MCP server on port 8001 (/mcp)"
  uvicorn eax.mcp_server:app --host 0.0.0.0 --port 8001 --no-access-log &
  MCP_PID=$!
else
  echo "EA Explorer: the MCP server is switched off (EAX_SERVICE_MCP=off)"
fi

# If either process stops, stop the other and exit so Docker restarts the container.
trap 'kill $API_PID $JOBS_PID $MCP_PID 2>/dev/null' TERM INT
while kill -0 $API_PID 2>/dev/null && kill -0 $JOBS_PID 2>/dev/null \
      && { [ -z "$MCP_PID" ] || kill -0 $MCP_PID 2>/dev/null; }; do
  sleep 2
done
echo "EA Explorer: a process stopped; exiting"
kill $API_PID $JOBS_PID $MCP_PID 2>/dev/null || true
exit 1
