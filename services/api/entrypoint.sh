#!/bin/sh
# EA Explorer api container.
#   EAX_ROLE=api (default): wait for the database, apply migrations and the job-queue schema,
#                           then run the web API (gunicorn) and the job runner side by side.
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

echo "EA Explorer: starting the API and the job runner"
gunicorn --bind 0.0.0.0:8000 --workers "${EAX_API_WORKERS:-2}" --access-logfile - "eax.wsgi:app" &
API_PID=$!
procrastinate --app=eax.jobs.app worker --concurrency "${EAX_JOB_CONCURRENCY:-2}" &
JOBS_PID=$!

# If either process stops, stop the other and exit so Docker restarts the container.
trap 'kill $API_PID $JOBS_PID 2>/dev/null' TERM INT
while kill -0 $API_PID 2>/dev/null && kill -0 $JOBS_PID 2>/dev/null; do
  sleep 2
done
echo "EA Explorer: a process stopped; exiting"
kill $API_PID $JOBS_PID 2>/dev/null || true
exit 1
