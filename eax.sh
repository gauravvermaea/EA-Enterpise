#!/usr/bin/env bash
# EA Explorer helper (Linux and macOS). Windows: use eax.ps1.  Run ./eax.sh help for every command.
#
# Everything local lives in the work folder, which is never committed: the config file
# (work/eaexplorer.env), the logs (work/logs) and laptop data (work/data: backups, imports, exports, tls).
set -euo pipefail
cd "$(dirname "$0")"
WORK_DIR=work
ENV_FILE=work/eaexplorer.env
LOG_DIR=work/logs
STAMP=$(date +%Y%m%d-%H%M%S)
LOG=""
CMD="${1:-help}"

# ------------------------------------------------------------------ help
help_text() {
cat <<'EOF'
EA Explorer helper. Usage: ./eax.sh <command> [options]      (Windows: .\eax.ps1 <command>)

Getting started
  init [laptop|server]  Creates work/eaexplorer.env from the template for the deployment kind
                        (laptop if not given) and the work folders. Nothing is generated: on a
                        laptop every password is P^55w0rd1234&; on a server, replace every change-me
                        value before starting. Refuses to overwrite an existing config file.
  check                 Checks that Docker is running and that the config file and compose files
                        are valid. Starts nothing.
  up [service...]       Builds our images, pulls the others, and starts every container in the
                        background. Then prints the addresses and (laptop) the logins.
                        Name services to start only those and what they depend on, for example
                        "up api" starts the API and PostgreSQL only (needs about 1 GB). On a laptop
                        the API is then at http://localhost:8000/api/docs.

Finding problems
  debug [service...]    Same as up, but does not stop on failure: it saves a diagnostics report and
                        then keeps recording the containers' output to
                        work/logs/containers-<date-time>.log until you press Ctrl+C.
                        The containers keep running after Ctrl+C. "debug api" starts and records
                        the API (and PostgreSQL) only.
  diag                  Saves a diagnostics report into this run's log: Docker versions, memory and
                        disk, image settings, every container's state, the last 300 log lines of
                        each container, and the compose configuration (passwords masked).
  status                Lists every container with its state and health, including stopped ones.
  logs [service]        Follows the logs of every container, or of one (for example: logs api).
                        Ctrl+C to stop.

Everyday use
  url                   Prints the addresses to open (and the logins on a laptop).
  logins                Prints every user name and password (laptop only).
  down                  Stops and removes the containers. Data in Docker volumes and in work/ is kept.
  backup                Takes a backup now into work/data/backups (laptop) or EAX_BACKUP_DIR.
  restore <folder> [--scratch]
                        Restores a backup folder: into the live databases, or with --scratch into
                        a separate scratch database to inspect first.

Starting again
  cleanup [--all] [--yes]
                        Stops the containers and deletes everything in the work folder: the config
                        file, logs and laptop data folders (including backups). With --all it also
                        deletes the Docker volumes, so the databases and documents start empty.
                        Asks you to type yes unless --yes is given. Run init afterwards.

  help [command]        This text, or the part about one command.

Logs: every command except help and cleanup writes its full output to
work/logs/eax-<date-time>-<command>.log. When a Docker step fails, a diagnostics report is added to
that log automatically, so the log file is all you need to send when something goes wrong.
EOF
}

show_help() {
  if [ -n "${1:-}" ]; then
    # the block for one command: its line and the indented lines under it
    help_text | awk -v c="$1" '
      $1 == c && /^  [a-z]/ { show = 1; print; next }
      show && /^                        / { print; next }
      { show = 0 }'
  else
    help_text
  fi
}

# ------------------------------------------------------------------ logging
start_log() {
  mkdir -p "$LOG_DIR"
  find "$LOG_DIR" -name '*.log' -mtime +14 -delete 2>/dev/null || true   # keep two weeks
  LOG="$LOG_DIR/eax-$STAMP-$CMD.log"
  exec 3>&1 4>&2                          # keep the plain console for "debug"
  exec > >(tee -a "$LOG") 2>&1            # everything from here on goes to the console and the log
  echo "=== eax $* $(date '+%Y-%m-%dT%H:%M:%S%z')   folder $(pwd)   $(uname -sr)"
  echo "Log: $LOG"
}

# Masks passwords, secrets and keys before config or container output reaches a log
mask() {
  sed -E -e 's/((PASSWORD|SECRET|_KEY|URLENC)[A-Z_]*[[:space:]]*[:=][[:space:]]*).*/\1****/' \
         -e 's#(redis://:)[^@]+@#\1****@#g' \
         -e 's/("PASSWORD"[[:space:]]*:[[:space:]]*")[^"]*"/\1****"/g'
}

# ------------------------------------------------------------------ settings and compose
# Value of a setting, without surrounding single or double quotes
setting() {
  local v
  v=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r') || true
  v="${v#\'}"; v="${v%\'}"; v="${v#\"}"; v="${v%\"}"
  echo "${v:-${2:-}}"
}
kind() { setting EAX_DEPLOYMENT laptop; }
compose() {
  [ -f "$ENV_FILE" ] || { echo "No $ENV_FILE yet: run ./eax.sh init first."; return 1; }
  # plain progress and no colour codes, so the log reads cleanly
  docker compose --ansi never --progress plain --env-file "$ENV_FILE" \
    -f docker-compose.yml -f "deploy/compose/docker-compose.$(kind).yml" "$@"
}

# Versions, containers, images, every container's recent log and the (masked) config, into the log only
diagnostics() {
  {
    echo; echo "==================== DIAGNOSTICS $(date '+%Y-%m-%dT%H:%M:%S%z') ===================="
    echo "> docker version"; docker version 2>&1 || true
    echo "> docker compose version"; docker compose version 2>&1 || true
    echo "> docker info"; docker info --format 'CPUs {{.NCPU}}  Memory {{.MemTotal}}  Storage {{.Driver}}  OS {{.OperatingSystem}}' 2>&1 || true
    echo "> docker system df"; docker system df 2>&1 || true
    if [ -f "$ENV_FILE" ]; then
      echo "> settings in $ENV_FILE (images, site, deployment)"
      grep -E '^EAX_(IMAGE_|DEPLOYMENT|HOSTNAME|HTTPS?_PORT|VERSION)|^COMPOSE_' "$ENV_FILE" || true
      echo "> compose ps -a"; compose ps -a 2>&1 || true
      echo "> compose images"; compose images 2>&1 || true
      for s in $(compose config --services 2>/dev/null); do
        echo "> compose logs $s"; compose logs --no-color --timestamps --tail 300 "$s" 2>&1 | mask || true
      done
      echo "> compose config (secrets masked)"; compose config 2>&1 | mask || true
    else
      echo "No $ENV_FILE: run ./eax.sh init first."
    fi
    echo "==================== END DIAGNOSTICS ===================="
  } >> "$LOG" 2>&1
  echo "Diagnostics saved in $LOG"
}

# Runs compose; on failure, adds diagnostics to the log and stops
run_compose() {
  if ! compose "$@"; then
    echo "docker compose failed. Collecting diagnostics..."
    diagnostics
    echo "ERROR: docker compose failed. Full log with diagnostics: $LOG"
    exit 1
  fi
}

# ------------------------------------------------------------------ output helpers
show_urls() {
  local H P S
  H=$(setting EAX_HOSTNAME localhost); P=$(setting EAX_HTTPS_PORT 443)
  S=$([ "$P" = "443" ] && echo "" || echo ":$P")
  echo "Start page:  https://$H$S/"
  echo "Swagger:     https://$H$S/api/docs"
  echo "Reports:     https://reports.$H$S/"
  echo "Documents:   https://docs.$H$S/"
  echo "Keycloak:    https://$H$S/auth/admin/"
  echo "Mail (dev):  https://$H$S/mail/"
}

show_logins() {
  if [ "$(kind)" != "laptop" ]; then
    echo "Logins are only printed for a laptop (development) installation. See $ENV_FILE."
    return 0
  fi
  echo
  echo "================ DEVELOPMENT LOGINS (laptop only - never use these on a server) ================"
  printf '%-34s %-14s %-16s %s\n' "Account" "User" "Password" "Notes"
  printf '%-34s %-14s %-16s %s\n' "EA Explorer (Keycloak realm)" "$(setting EAX_FIRST_ADMIN_USER eaadmin)" "$(setting EAX_FIRST_ADMIN_PASSWORD)" "start page sign-in; Superset and Mayan via SSO"
  printf '%-34s %-14s %-16s %s\n' "Keycloak administrator" "$(setting EAX_KC_ADMIN kcadmin)" "$(setting EAX_KC_ADMIN_PASSWORD)" "/auth/admin/ (master realm)"
  printf '%-34s %-14s %-16s %s\n' "Superset break-glass admin" "admin" "$(setting EAX_SUPERSET_ADMIN_PASSWORD)" "only when EAX_SUPERSET_AUTH=db"
  printf '%-34s %-14s %-16s %s\n' "Mayan EDMS administrator" "$(setting EAX_MAYAN_ADMIN_USER admin)" "$(setting EAX_MAYAN_ADMIN_PASSWORD)" "local Mayan account"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL superuser" "postgres" "$(setting EAX_DB_SUPERUSER_PASSWORD)" "docker compose exec db psql -U postgres"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL EA Explorer" "eax_app" "$(setting EAX_DB_PASSWORD)" "database $(setting EAX_DB_NAME eaexplorer)"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL reporting (read only)" "eax_report" "$(setting EAX_DB_REPORT_PASSWORD)" "schema rpt"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Keycloak" "keycloak" "$(setting EAX_KEYCLOAK_DB_PASSWORD)" "database keycloak"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Superset" "superset" "$(setting EAX_SUPERSET_DB_PASSWORD)" "database superset"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Mayan" "mayan" "$(setting EAX_MAYAN_DB_PASSWORD)" "database mayan"
  printf '%-34s %-14s %-16s %s\n' "Valkey cache" "(none)" "$(setting EAX_CACHE_PASSWORD)" "password only"
  printf '%-34s %-14s %-16s %s\n' "Keycloak client secrets" "superset/mayan" "$(setting EAX_SUPERSET_OIDC_SECRET)" "OIDC clients"
  echo "================================================================================================="
}

# Follows every container's log into work/logs/containers-<stamp>.log (and the console) until Ctrl+C
show_part_urls() {
  echo
  echo "Started: $* (and what they depend on). The rest stays stopped."
  case " $* " in *" api "*)
    echo "API directly (laptop, no proxy or sign-in needed for public endpoints):"
    echo "  Swagger:    http://localhost:8000/api/docs"
    echo "  Heartbeat:  http://localhost:8000/api/v1/heartbeat" ;;
  esac
  echo "Stop everything with ./eax.sh down"
}

watch_containers() {
  local f="$LOG_DIR/containers-$STAMP.log"
  echo
  echo "Recording every container's log to $f"
  echo "Leave this window open while you test; press Ctrl+C to stop recording (the containers keep running)."
  compose logs -f --no-color --timestamps --tail 500 "$@" 2>&1 | mask | tee -a "$f" >&3 || true
}

# Stops the containers and empties the work folder (no log: the logs folder is being deleted)
cleanup() {
  local all=false yes=false a
  for a in "$@"; do
    case "$a" in --all) all=true ;; --yes|-y) yes=true ;; *) echo "ERROR: unknown option $a"; exit 1 ;; esac
  done
  echo "This deletes everything in $(pwd)/$WORK_DIR: the config file, all logs and the laptop data folders (including backups)."
  $all && echo "With --all it also deletes the Docker volumes: the databases and documents start empty."
  if ! $yes; then
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing deleted."; exit 0; }
  fi
  if [ -f "$ENV_FILE" ]; then
    if $all; then compose down -v --remove-orphans || true; else compose down --remove-orphans || true; fi
  elif $all; then
    echo "No $ENV_FILE, so the Docker volumes cannot be found by name; remove them with: docker volume ls"
  fi
  rm -rf "${WORK_DIR:?}"/* "${WORK_DIR:?}"/.[!.]* 2>/dev/null || true
  echo "The work folder is empty. Run ./eax.sh init laptop to start again."
}

# Stops early with a plain message when the Docker engine is not reachable
assert_docker() {
  if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
    echo "ERROR: Docker is not running (or still starting). Start Docker Desktop or the Docker service, check with: docker version (it must show a Server section), then run this again."
    exit 1
  fi
}

# ------------------------------------------------------------------ commands
case "$CMD" in
  help|-h|--help) show_help "${2:-}"; exit 0 ;;
  cleanup)        shift; cleanup "$@"; exit 0 ;;
esac

start_log "$@"
if [ -f eaexplorer.env ] && [ ! -f "$ENV_FILE" ]; then
  echo "Found eaexplorer.env in the main folder: it is no longer used. The config now lives in $ENV_FILE."
  echo "Delete the old file and run ./eax.sh init laptop (or copy your changes into $ENV_FILE)."
fi

case "$CMD" in check|up|debug|status|logs|down|backup|restore) assert_docker ;; esac

case "$CMD" in
  init)
    K="${2:-laptop}"
    [ -f "$ENV_FILE" ] && { echo "ERROR: $ENV_FILE already exists; not overwriting. Use ./eax.sh cleanup to start again."; exit 1; }
    [ -f "deploy/templates/eaexplorer.$K.env" ] || { echo "ERROR: unknown deployment kind: $K"; exit 1; }
    mkdir -p work/logs work/data/backups work/data/imports work/data/exports work/data/tls
    # Plain copy with LF endings: no passwords are generated
    tr -d '\r' < "deploy/templates/eaexplorer.$K.env" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Created $ENV_FILE ($K) from deploy/templates/eaexplorer.$K.env."
    if [ "$K" = "laptop" ]; then show_logins
    else echo "Now replace every change-me value in $ENV_FILE with your own passwords before ./eax.sh up."; fi
    ;;
  check)
    docker version --format 'Docker {{.Server.Version}}' || { echo "ERROR: Docker is not running."; exit 1; }
    docker compose version
    [ -f "$ENV_FILE" ] || { echo "ERROR: no $ENV_FILE yet: run ./eax.sh init"; exit 1; }
    echo "Config: $ENV_FILE ($(kind))"
    run_compose config --quiet && echo "Compose configuration is valid."
    ;;
  up)
    shift
    run_compose up -d --build "$@"
    if [ "$#" -gt 0 ]; then show_part_urls "$@"; else show_urls; show_logins; fi
    ;;
  debug)
    shift
    if ! compose up -d --build "$@"; then echo "docker compose up failed; recording what is running anyway."; fi
    diagnostics
    if [ "$#" -gt 0 ]; then show_part_urls "$@"; else show_urls; show_logins; fi
    watch_containers "$@"
    ;;
  diag)    diagnostics ;;
  status)  run_compose ps -a ;;
  logs)    shift; compose logs -f --tail=100 "$@" || true ;;
  down)    run_compose down ;;
  backup)  run_compose exec -T backup backup.sh ;;
  restore) shift; run_compose exec -T backup restore.sh "$@" ;;
  url)     show_urls; show_logins ;;
  logins)  [ -f "$ENV_FILE" ] || { echo "ERROR: no $ENV_FILE yet: run ./eax.sh init first."; exit 1; }; show_logins ;;
  *)       echo "ERROR: unknown command '$CMD'. Run ./eax.sh help"; exit 1 ;;
esac
echo "Log: $LOG"
