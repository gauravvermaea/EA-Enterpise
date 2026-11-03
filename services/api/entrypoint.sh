#!/bin/sh
# EA Explorer api container.
#   EAX_ROLE=api (default): wait for the database, apply migrations and the job-queue schema,
#                           then run the web API (gunicorn), the job runner and (EAX_MCP_ENABLED) the MCP
#                           server (uvicorn, port 8001) side by side.
#   any other command:      run it as given (the setup service uses: python -m eax.setup).
set -eu
cd /app

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python -m eax.wait_for_db
echo "EA Explorer: applying database migrations"
alembic upgrade head
python -m eax.jobs_schema
python -m eax.seed

echo "EA Explorer: starting the API and the job runner"
gunicorn --bind 0.0.0.0:8000 --workers "${EAX_API_WORKERS:-2}" --access-logfile - "eax.wsgi:app" &
API_PID=$!
procrastinate --app=eax.jobs.app worker --concurrency "${EAX_JOB_CONCURRENCY:-2}" &
JOBS_PID=$!
MCP_PID=""
case "${EAX_MCP_ENABLED:-false}" in
  true|TRUE|True|1|yes)
    echo "EA Explorer: starting the MCP server on port 8001 (/mcp)"
    uvicorn eax.mcp_server:app --host 0.0.0.0 --port 8001 --no-access-log &
    MCP_PID=$! ;;
esac

# If either process stops, stop the other and exit so Docker restarts the container.
trap 'kill $API_PID $JOBS_PID $MCP_PID 2>/dev/null' TERM INT
while kill -0 $API_PID 2>/dev/null && kill -0 $JOBS_PID 2>/dev/null \
      && { [ -z "$MCP_PID" ] || kill -0 $MCP_PID 2>/dev/null; }; do
  sleep 2
done
echo "EA Explorer: a process stopped; exiting"
kill $API_PID $JOBS_PID $MCP_PID 2>/dev/null || true
exit 1
