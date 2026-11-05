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
[ "$CMD" = run ] && CMD=up   # run: the everyday start, the same as up

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
  run                   The everyday start, after the first clean-run: the same as up. Keeps the
                        databases, documents and settings from last time.
  up [service...]       Builds our images, pulls the others, and starts every container in the
                        background. Then prints the addresses and (laptop) the logins.
                        Name services to start only those and what they depend on, for example
                        "up api proxy" starts the API, PostgreSQL and nginx only (about 1 GB);
                        the API is then at https://localhost/api/docs (laptop also http://).

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
  trust [--remove]      Adds EA Explorer's local certificate (work/data/tls/ca.crt) to this computer's
                        trusted certificates (macOS: your login keychain; Linux: prints the commands,
                        which need sudo), so the browser stops warning. Once: clean-run keeps it.
  logins                Prints every user name and password (laptop only).
  down                  Stops and removes the containers. Data in Docker volumes and in work/ is kept.
  backup                Takes a backup now into work/data/backups (laptop) or EAX_BACKUP_DIR.
  restore <folder> [--scratch]
                        Restores a backup folder: into the live databases, or with --scratch into
                        a separate scratch database to inspect first.

Starting again
  cleanup [--all] [--yes] [--certificate]
                        Stops the containers and deletes everything in the work folder: the config
                        file, logs and laptop data folders (including backups). With --all it also
                        deletes the Docker volumes, so the databases and documents start empty.
                        The local certificate (work/data/tls) is kept, so you need not trust it
                        again; --certificate deletes it too. Asks you to type yes unless --yes is given.
  clean-run [laptop|server]
                        Starts again from scratch in one step: cleanup --all --yes, then init
                        (laptop if not given), then up. Deletes the databases and everything in
                        the work folder without asking.
  clean-debug [laptop|server]
                        The same, but ends with debug instead of up (keeps recording the
                        containers' output until Ctrl+C).
  clean-restart [laptop|server]
                        For testing a new version: down (stops and removes the running containers),
                        then clean-run (cleanup --all --yes, init, up). Rebuilds our images and
                        starts with empty databases; the trusted certificate is kept.

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
  [ "$(setting EAX_MCP_ENABLED false)" = "true" ] && echo "MCP server:  https://$H$S/mcp"
  if [ "$(setting EAX_HTTP_API_MCP false)" = "true" ]; then
    local HP; HP=$(setting EAX_HTTP_PORT 80); [ "$HP" = "80" ] && HP="" || HP=":$HP"
    echo "Also on plain http (this computer only): http://localhost$HP/api/docs and http://localhost$HP/mcp"
  fi
  return 0
}

# ------------------------------------------------------------------ the local certificate (D107)
ca_path() {
  local d; d=$(setting EAX_TLS_DIR ./work/data/tls)
  case "$d" in */*) echo "$d/ca.crt" ;; *) echo "" ;; esac
}
trust() {
  local ca; ca=$(ca_path)
  [ -n "$ca" ] || { echo "ERROR: EAX_TLS_DIR is a Docker volume; copy ca.crt out with: docker compose cp setup:/tls/ca.crt ."; exit 1; }
  if [ "${1:-}" = "--remove" ]; then
    if [ "$(uname)" = Darwin ]; then
      while security delete-certificate -c "EA Explorer local CA" ~/Library/Keychains/login.keychain-db >/dev/null 2>&1; do :; done
      echo "Removed EA Explorer certificates from your login keychain."
    else
      echo "Run: sudo rm -f /usr/local/share/ca-certificates/eaexplorer-local-ca.crt && sudo update-ca-certificates --fresh"
    fi
    return 0
  fi
  [ -f "$ca" ] || { echo "ERROR: no $ca yet: run ./eax.sh up first (the setup service makes it)."; exit 1; }
  if [ "$(uname)" = Darwin ]; then
    while security delete-certificate -c "EA Explorer local CA" ~/Library/Keychains/login.keychain-db >/dev/null 2>&1; do :; done
    security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db "$ca"
    echo "Trusted (macOS asks for your password). Restart the browser."
  else
    echo "Run: sudo cp $ca /usr/local/share/ca-certificates/eaexplorer-local-ca.crt && sudo update-ca-certificates"
    echo "Chrome and Firefox on Linux keep their own lists: import $ca there (Settings > Certificates > Authorities)."
  fi
  echo "MCP clients that run on Node (Claude Code, mcp-remote): export NODE_EXTRA_CA_CERTS=\"$(pwd)/$ca\""
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
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL installer" "eax_migrator" "$(setting EAX_DB_MIGRATOR_PASSWORD)" "loads reference models only"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Keycloak" "keycloak" "$(setting EAX_KEYCLOAK_DB_PASSWORD)" "database keycloak"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Superset" "superset" "$(setting EAX_SUPERSET_DB_PASSWORD)" "database superset"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Mayan" "mayan" "$(setting EAX_MAYAN_DB_PASSWORD)" "database mayan"
  printf '%-34s %-14s %-16s %s\n' "Mayan broker (Valkey)" "(none)" "$(setting EAX_DMS_BROKER_PASSWORD)" "password only"
  printf '%-34s %-14s %-16s %s\n' "MCP server (development token)" "(bearer)" "$(setting EAX_MCP_DEV_TOKEN)" "https://localhost/mcp or http://localhost/mcp"
  printf '%-34s %-14s %-16s %s\n' "Keycloak client secrets" "superset/mayan" "$(setting EAX_SUPERSET_OIDC_SECRET)" "OIDC clients"
  printf '%-34s %-14s %-16s %s\n' "Keycloak API client (eax-admin)" "eax-admin" "$(setting EAX_KC_SERVICE_SECRET)" "reads people and roles"
  printf '%-34s %-14s %-16s %s\n' "Break-glass account" "break-glass" "$(setting EAX_BREAK_GLASS_PASSWORD)" "when Keycloak is down: start page"
  local tpw; tpw="$(setting EAX_TEST_USER_PASSWORD)"; [ -n "$tpw" ] || tpw="$(setting EAX_FIRST_ADMIN_PASSWORD)"
  echo "Test users (phase 3.1): global role in Keycloak; model roles given per model in EA Explorer:"
  for row in "user_super_admin|eax-super-admin|everything, every model" \
             "user_it_admin|eax-it-admin|runs the installation; no models" \
             "user_keycloak_admin|eax-keycloak-admin|Keycloak console of the realm" \
             "user_user_admin|eax-user-admin|Users page, role mapping; reads no model" \
             "user_library_admin|eax-library-admin|curates the model library: create, publish, promote, upload, withdraw" \
             "user_model_creator|eax-model-creator|creates models; Model Admin: Karoo Re, Lean EA metamodel, Karoo Digital" \
             "user_model_admin|eax-user|Model Admin: Fynbos group, Fynbos Life, Protea demo; Architect: Sample" \
             "user_architect|eax-user|Architect: Sample, Fynbos Life, Protea demo; Model Sub Admin + Report Viewer: Fynbos Commercial" \
             "user_model_sub_admin|eax-user|Model Sub Admin: Sample, Fynbos Life, Fynbos Commercial, Karoo Re" \
             "user_committer|eax-user|Committer: Protea demo, Sample (commits what others ask to commit)" \
             "user_history_viewer|eax-user|History Viewer and Report Viewer: Protea demo (sees everyone's commits)" \
             "user_report_viewer|eax-user|Report Viewer: Fynbos group, Sample, Protea demo" \
             "user_global_architect|eax-user|Architect on every model"; do
    IFS='|' read -r u r n <<< "$row"
    printf '  %-32s %-22s %-16s %s\n' "$r" "$u" "$tpw" "$n"
  done
  echo "================================================================================================="
}

# Follows every container's log into work/logs/containers-<stamp>.log (and the console) until Ctrl+C
show_part_urls() {
  echo
  echo "Started: $* (and what they depend on). The rest stays stopped."
  case " $* " in *" api "*)
    echo "The API goes through nginx: start it too with  ./eax.sh up api proxy  (no Keycloak needed for public endpoints):"
    echo "  Swagger:    https://localhost/api/docs   (laptop also http://localhost/api/docs)"
    echo "  Heartbeat:  https://localhost/api/v1/heartbeat" ;;
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
  local all=false yes=false cert=false a
  for a in "$@"; do
    case "$a" in --all) all=true ;; --yes|-y) yes=true ;; --certificate) cert=true ;; *) echo "ERROR: unknown option $a"; exit 1 ;; esac
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
  if $cert; then
    rm -rf "${WORK_DIR:?}"/* "${WORK_DIR:?}"/.[!.]* 2>/dev/null || true
    echo "The work folder is empty. Run ./eax.sh init laptop to start again."
  else
    # keep work/data/tls: the local certificate you trusted with ./eax.sh trust (D107)
    find "${WORK_DIR:?}" -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf {} + 2>/dev/null || true
    [ -d "$WORK_DIR/data" ] && find "$WORK_DIR/data" -mindepth 1 -maxdepth 1 ! -name tls -exec rm -rf {} + 2>/dev/null || true
    echo "The work folder is empty apart from the local certificate (work/data/tls). Run ./eax.sh init laptop to start again."
  fi
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
  clean-run|clean-debug|clean-restart)
    # cleanup --all --yes, init, then up or debug: each as its own run of this script (own log);
    # clean-restart brings the running containers down first
    kind="${2:-laptop}"; last=up; [ "$CMD" = clean-debug ] && last=debug
    steps=("cleanup --all --yes" "init $kind" "$last")
    if [ "$CMD" = clean-restart ]; then
      if [ -f "$ENV_FILE" ]; then steps=("down" "${steps[@]}")
      else echo "No $ENV_FILE yet: nothing running to bring down; going straight to clean-run."; fi
    fi
    for step in "${steps[@]}"; do
      echo; echo "=== ./eax.sh $step"
      # shellcheck disable=SC2086
      "$BASH" "./$(basename "${BASH_SOURCE[0]}")" $step || { echo "ERROR: ./eax.sh $step failed; $CMD stopped there."; exit 1; }
    done
    exit 0 ;;
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
  trust)   [ -f "$ENV_FILE" ] || { echo "ERROR: no $ENV_FILE yet: run ./eax.sh init first."; exit 1; }; trust "${2:-}" ;;
  *)       echo "ERROR: unknown command '$CMD'. Run ./eax.sh help"; exit 1 ;;
esac
echo "Log: $LOG"
