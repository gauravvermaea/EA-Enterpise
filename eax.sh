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
# --no-color anywhere: plain text (R2.10); colour only on a terminal, never with NO_COLOR or CI set, never when piped
_plain=""
_args=()
for _a in "$@"; do if [ "$_a" = --no-color ]; then _plain=1; else _args+=("$_a"); fi; done
set -- ${_args[@]+"${_args[@]}"}
C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_GREY=""; C_OFF=""
if [ -z "$_plain" ] && [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ -z "${EAX_NO_COLOR:-}" ] && [ -z "${CI:-}" ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_CYAN=$'\033[36m'; C_GREY=$'\033[90m'; C_OFF=$'\033[0m'
fi
err()     { printf '%s\n' "${C_RED}ERROR: $*${C_OFF}"; }
warn()    { printf '%s\n' "${C_YELLOW}$*${C_OFF}"; }
ok()      { printf '%s\n' "${C_GREEN}$*${C_OFF}"; }
heading() { printf '%s\n' "${C_CYAN}$*${C_OFF}"; }
# each `docker compose ps` line in its state's colour (the same rule as eaxcli/core.py state_colour)
colour_status() {
  local first=1 line low c
  while IFS= read -r line; do
    if [ -n "$first" ]; then printf '%s\n' "$line"; first=""; continue; fi
    low=$(printf '%s' "$line" | tr '[:upper:]' '[:lower:]'); c=""
    case "$low" in
      *setup*"exited (0"*|*reports-init*"exited (0"*) c=$C_GREY ;;
      *unhealthy*|*" dead"*|*restarting*|*oomkilled*) c=$C_RED ;;
      *"exited (0"*) c=$C_GREY ;;
      *exited*) c=$C_RED ;;
      *"health: starting"*|*starting*|*created*|*paused*|*removing*) c=$C_YELLOW ;;
      *"up "*|*running*|*"(healthy)"*) c=$C_GREEN ;;
    esac
    printf '%s\n' "${c}${line}${c:+$C_OFF}"
  done
}
# no command on a terminal: the numbered menu (R2.29); piped or in a script: the help, as before
if [ "$#" -eq 0 ]; then if [ -t 0 ]; then set -- menu; else set -- help; fi; fi
CMD="${1:-help}"
# <command> --help (or -h, /?): the help of that command
if [ "$CMD" != help ] && [ "$CMD" != -h ] && [ "$CMD" != --help ]; then
  for _a in "${@:2}"; do case "$_a" in --help|-h|/\?) CMD=help; set -- help "$1"; break ;; esac; done
fi
[ "$CMD" = run ] && CMD=up   # run: the everyday start, the same as up
[ "$CMD" = stop ] && CMD=down   # stop: the same as down (the data is kept)
# --wait-all (up, run, debug and the clean-* commands): start everything and wait until all of it is up, the sample data
# loaded too; without it the core starts first and the rest in the background (D255)
WAIT_ALL=""
_args=()
for _a in "$@"; do if [ "$_a" = --wait-all ]; then WAIT_ALL=1; else _args+=("$_a"); fi; done
set -- "${_args[@]}"

# ------------------------------------------------------------------ help
# The help is read from eaxcli/help.txt, the one source for every form of eax (D331; tests/test_eax_help.py):
# show_help prints the overview, one command in full (show_help stop) or everything (show_help --all).
show_help() {
  awk -v form=sh -v eax="./eax.sh" -v want="${1:-}" -v arg="${2:-}" '
    function rep(s,   i, o) { o = ""; while ((i = index(s, "{eax}")) > 0) { o = o substr(s, 1, i - 1) eax; s = substr(s, i + 5) } return o s }
    function out(s) { print rep(s) }
    function block(c,   n, nm, h, k) {
      n = split(cnames[c], nm, "|"); h = "  " nm[1]; if (cargs[c] != "") h = h " " cargs[c]
      if (n > 1) { h = h "   (also: " nm[2]; for (k = 3; k <= n; k++) h = h ", " nm[k]; h = h ")" }
      out(h); out("    " csum[c])
      for (k = 1; k <= cd[c]; k++) out("    " cdet[c, k])
      if (ce[c] > 0) { out("    Examples:"); for (k = 1; k <= ce[c]; k++) out("      " cex[c, k]) }
    }
    BEGIN { where = "intro"; ns = 0; nc = 0; ni = 0; nf = 0; nintro = 0; cur = 0 }
    {
      line = $0; sub(/[ \t\r]+$/, "", line)
      if (substr(line, 1, 1) == ";") next
      if (match(line, /^\[(win|unix|ps1|sh|py)\]/)) {
        tag = substr(line, 2, RLENGTH - 2)
        if (tag != form && tag != "unix") next
        line = substr(line, RLENGTH + 1); if (substr(line, 1, 1) == " ") line = substr(line, 2)
      }
      if (where == "footer") { foot[++nf] = line; next }
      if (line == "@footer") { where = "footer"; next }
      if (substr(line, 1, 10) == "@internal ") {
        r = substr(line, 11); p = index(r, " "); ni++; iname[ni] = substr(r, 1, p - 1); iwhat[ni] = substr(r, p + 1); next
      }
      if (substr(line, 1, 3) == "## ") { ns++; stitle[ns] = substr(line, 4); snotes[ns] = 0; where = "section"; cur = 0; next }
      if (substr(line, 1, 4) == "### ") {
        r = substr(line, 5); p = index(r, " ")
        nc++; if (p) { cnames[nc] = substr(r, 1, p - 1); cargs[nc] = substr(r, p + 1) } else { cnames[nc] = r; cargs[nc] = "" }
        csec[nc] = ns; cd[nc] = 0; ce[nc] = 0; csum[nc] = ""; cur = nc; next
      }
      if (where == "intro") { if (line != "") intro[++nintro] = line; next }
      if (substr(line, 1, 2) == ": " && cur == 0) { snotes[ns]++; snote[ns, snotes[ns]] = substr(line, 3); next }
      if (cur == 0) next
      if (substr(line, 1, 2) == "> ") { csum[cur] = substr(line, 3); next }
      if (substr(line, 1, 2) == "$ ") { ce[cur]++; cex[cur, ce[cur]] = substr(line, 3); next }
      if (line != "") { cd[cur]++; cdet[cur, cd[cur]] = line }
    }
    function text(c,   n, nm, k, t) {
      n = split(cnames[c], nm, "|"); t = nm[1]; for (k = 2; k <= n; k++) t = t " " nm[k]
      t = t " " cargs[c] " " csum[c]
      for (k = 1; k <= cd[c]; k++) t = t " " cdet[c, k]
      for (k = 1; k <= ce[c]; k++) t = t " " cex[c, k]
      return tolower(t)
    }
    END {
      while (nf > 0 && foot[nf] == "") nf--
      if (want == "--groups") { for (s = 1; s <= ns; s++) out(sprintf("%4d  %s", s, stitle[s])); exit 0 }
      if (want == "--group") {
        n = (arg ~ /^[0-9]+$/) ? arg + 0 : 0
        if (n < 1 || n > ns) { out("No group " arg "."); exit 1 }
        out(stitle[n]); for (k = 1; k <= snotes[n]; k++) out("  " snote[n, k])
        for (c = 1; c <= nc; c++) if (csec[c] == n) { out(""); block(c) }
        exit 0
      }
      if (want == "--search") {
        w = tolower(arg); found = 0
        for (c = 1; c <= nc; c++) if (w != "" && index(text(c), w) > 0) { if (found) out(""); block(c); found = 1 }
        if (!found) { out("Nothing found for '\''" arg "'\''."); exit 1 }
        exit 0
      }
      if (want == "" || want == "--all") {
        for (i = 1; i <= nintro; i++) out(intro[i])
        for (s = 1; s <= ns; s++) {
          out(""); out(stitle[s])
          for (k = 1; k <= snotes[s]; k++) out("  " snote[s, k])
          for (c = 1; c <= nc; c++) {
            if (csec[c] != s) continue
            if (want != "") { out(""); block(c); continue }
            lab = cnames[c]; gsub(/\|/, ", ", lab); if (cargs[c] != "") lab = lab " " cargs[c]
            if (length(lab) <= 20) out(sprintf("  %-22s%s", lab, csum[c]))
            else { out("  " lab); out(sprintf("%24s%s", "", csum[c])) }
          }
        }
        if (want != "" && ni > 0) {
          out(""); out("Internal (run by eax itself; not for typing)")
          for (i = 1; i <= ni; i++) out(sprintf("  %-22s%s", iname[i], iwhat[i]))
        }
        out(""); for (i = 1; i <= nf; i++) out(foot[i])
        exit 0
      }
      for (c = 1; c <= nc; c++) {
        n = split(cnames[c], nm, "|")
        for (k = 1; k <= n; k++) if (nm[k] == want) { block(c); exit 0 }
      }
      for (i = 1; i <= ni; i++) if (iname[i] == want) { out("  " iname[i]); out("    " iwhat[i]); exit 0 }
      out("No command '\''" want "'\''. Run {eax} help to list them."); exit 1
    }' eaxcli/help.txt
}

# eax document (D331): every command in full, from eaxcli/help.txt, as a web page (eaxcli/document.html with the help
# copied in; eaxpy and eax.ps1 make the same file) or in the console (a menu of the groups, page by page)
document_web() {
  mkdir -p work/docs
  local out=work/docs/eax-commands.html
  awk -v form=sh -v eax="./eax.sh" -v win=false -v helpfile=eaxcli/help.txt '
    function rep(s, k, v,   i, o) { o = ""; while ((i = index(s, k)) > 0) { o = o substr(s, 1, i - 1) v; s = substr(s, i + length(k)) } return o s }
    { sub(/\r$/, "") }
    $0 == "__HELP__" { while ((getline l < helpfile) > 0) { sub(/\r$/, "", l); print l } next }
    { print rep(rep(rep($0, "__FORM__", form), "__EAX__", eax), "__WINDOWS__", win) }' eaxcli/document.html > "$out"
  echo "The commands as a web page: $out"
  [ -n "${EAX_NO_BROWSER:-}" ] && return 0
  if [ "$(uname)" = Darwin ]; then open "$out"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$out" >/dev/null 2>&1 || echo "Open it in your browser."
  else echo "Open it in your browser."; fi
}

page_out() {
  local n=0 rows k line
  rows=$(( $(tput lines 2>/dev/null || echo 24) - 2 )); [ "$rows" -lt 10 ] && rows=10
  while IFS= read -r line; do
    printf '%s\n' "$line"; n=$((n + 1))
    if [ "$n" -ge "$rows" ] && [ -t 1 ]; then      # pages only on a terminal (piped or tested: all of it)
      n=0; read -r -p "-- Enter for more, q to stop -- " k </dev/tty || break
      [ "$k" = q ] && break
    fi
  done
}

document_console() {
  local a w
  while true; do
    echo; echo "EA Explorer commands (./eax.sh document)"; show_help --groups
    read -r -p "Number, s to search, q to quit: " a || return 0
    case "$a" in
      q|Q) return 0 ;;
      s|S) read -r -p "Search for: " w || return 0; { show_help --search "$w" || true; } | page_out ;;
      "") ;;
      *[!0-9]*) echo "Choose a number, s or q." ;;
      *) { show_help --group "$a" || true; } | page_out ;;
    esac
  done
}

document() {
  local mode="" a
  for a in "$@"; do case "$a" in --console) mode=console ;; --web) mode=web ;; esac; done
  if [ -z "$mode" ]; then
    read -r -p "Show the commands (1) here in the console or (2) as a web page in your browser? [1/2] " a || a=1
    case "$a" in 2|w|web) mode=web ;; *) mode=console ;; esac
  fi
  if [ "$mode" = web ]; then document_web; else document_console; fi
}

# ------------------------------------------------------------------ logging
start_log() {
  mkdir -p "$LOG_DIR"
  find "$LOG_DIR" -name '*.log' -mtime +14 -delete 2>/dev/null || true   # keep two weeks
  LOG="$LOG_DIR/eax-$STAMP-$CMD.log"
  exec 3>&1 4>&2                          # keep the plain console for "debug"
  # everything from here on goes to the console and the log (the log without colour codes, R2.10)
  exec > >(tee >(awk '{ gsub(/\033\[[0-9;]*m/, ""); print; fflush() }' >> "$LOG")) 2>&1
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
# the build shown with the release (R2.47): EAX_BUILD as CI sets it, else the commit's short id ("-changed" when files
# differ from it), "dev" outside git; the commit and its time, so the API container is made again only when they change
build_id() {
  if [ -n "${EAX_BUILD:-}" ]; then echo "$EAX_BUILD"; return; fi
  c=$(git rev-parse --short HEAD 2>/dev/null) || { echo dev; return; }
  if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then c="$c-changed"; fi
  echo "$c"
}
release() { sed -n 's/^version *= *"\(.*\)"/\1/p' services/api/version.toml 2>/dev/null; }
compose() {
  [ -f "$ENV_FILE" ] || { echo "No $ENV_FILE yet: run ./eax.sh init first."; return 1; }
  EAX_BUILD=$(build_id); EAX_COMMIT=${EAX_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}
  EAX_BUILT_AT=${EAX_BUILT_AT:-$(git log -1 --format=%cI 2>/dev/null || true)}
  export EAX_BUILD EAX_COMMIT EAX_BUILT_AT
  # plain progress and no colour codes, so the log reads cleanly
  # scale-out extra files (phase 36.3, D521): EAX_COMPOSE_EXTRA=standby,shared-storage... (deploy/compose/scale)
  set -- $(compose_extra) "$@"
  docker compose --ansi never --progress plain --env-file "$ENV_FILE" \
    -f docker-compose.yml -f "deploy/compose/docker-compose.$(kind).yml" "$@"
}
compose_extra() {
  for x in $(setting EAX_COMPOSE_EXTRA "" | tr ',' ' '); do
    f="deploy/compose/scale/docker-compose.$x.yml"
    [ -f "$f" ] || { echo "EAX_COMPOSE_EXTRA names $x, but there is no $f." >&2; return 1; }
    printf -- '-f %s ' "$f"
  done
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
# the file systems after the containers (owner, 8 Nov 2026): read by the operations helper, and this machine's disk here
show_filesystems() {
  echo
  if [ -n "$(compose ps --status running -q ops 2>/dev/null)" ]; then
    compose exec -T ops python3 /app/ops.py filesystems 2>/dev/null || true
  else
    echo "File systems: the operations helper is not running, so Docker's disk is not read (docker system df below)."
    docker system df 2>/dev/null | sed 's/^/  /' || true
  fi
  echo "  This machine's disk for the project folder:"
  df -h "$(dirname "$0")" 2>/dev/null | sed 's/^/    /' || true
}

run_compose() {
  if ! compose "$@"; then
    echo "docker compose failed. Collecting diagnostics..."
    diagnostics
    err "docker compose failed. Full log with diagnostics: $LOG"
    exit 1
  fi
}

# ------------------------------------------------------------------ optional services (D191)
SERVICE_NAMES="reports documents drawio mcp change_log backups library views"
service_setting() {
  case "$1" in reports) echo EAX_SERVICE_REPORTS ;; documents) echo EAX_SERVICE_DOCUMENTS ;; drawio) echo EAX_SERVICE_DRAWIO ;;
    mcp) echo EAX_SERVICE_MCP ;; change_log) echo EAX_SERVICE_CHANGE_LOG ;; backups) echo EAX_SERVICE_BACKUPS ;;
    library) echo EAX_SERVICE_LIBRARY ;; views) echo EAX_SERVICE_VIEWS ;; *) return 1 ;; esac
}
# compose services in start order (mcp and change_log run inside the api container)
service_containers() {
  case "$1" in reports) echo "reports-init reports" ;; documents) echo "dms-broker dms" ;; drawio) echo drawio ;;
    mcp|change_log) echo api ;; backups) echo backup ;; library) echo library ;; views) echo views ;; esac
}
service_on() {
  local d=on v
  [ "$1" = mcp ] && d=$(setting EAX_MCP_ENABLED on)
  v=$(setting "$(service_setting "$1")" "$d" | tr '[:upper:]' '[:lower:]')
  case "$v" in off|false|0|no|disabled) return 1 ;; *) return 0 ;; esac
}
# work/services.env: the switches only (no secrets), read by the api container
write_services_file() {
  local n
  { echo "# Written by EA Explorer from eaexplorer.env: the service switches only (D191). Do not edit; change eaexplorer.env."
    for n in $SERVICE_NAMES; do echo "$(service_setting "$n")=$(service_on "$n" && echo on || echo off)"; done
  } > "$WORK_DIR/services.env"
  chmod 644 "$WORK_DIR/services.env"
}
off_containers() {
  local n out=""
  for n in $SERVICE_NAMES; do
    service_on "$n" && continue
    [ "$(service_containers "$n")" = api ] && continue
    out="$out $(service_containers "$n")"
  done
  echo "$out"
}
# up (all services): everything but the switched-off services; those are created, not started, so the console can
# switch them on later
# how many API and job servers (copies of the api container) run (D249): 1 to 16, 1 when not set
api_servers() {
  local n; n=$(setting EAX_API_SERVERS 1)
  case "$n" in ''|*[!0-9]*) n=1 ;; esac
  [ "$n" -lt 1 ] && n=1; [ "$n" -gt 16 ] && n=16
  echo "$n"
}
# The start-up in two tiers (D255): the core first (database, set-up, proxy, screens, sign-in, the API with the database
# upgrade and the built-in models), so people can sign in in a minute or two; everything else after it, in the
# background (Reports, Documents, draw.io, backups, the operations helper), while the API loads the sample data and
# measures data quality. The screens show each part red, amber or green (down, starting, up).
CORE_SERVICES="db setup proxy web keycloak api"
tiers() {  # sets FIRST, LATER and OFF
  local s
  OFF=$(off_containers); FIRST=""; LATER=""
  for s in $(compose config --services); do
    case " $OFF " in *" $s "*) continue ;; esac
    case " $CORE_SERVICES " in *" $s "*) FIRST="$FIRST $s" ;; *) LATER="$LATER $s" ;; esac
  done
}
# waits until the API (every copy) and Keycloak say healthy; shows each change
wait_core() {
  local until=$(( $(date +%s) + 900 )) last="" rows now
  while [ "$(date +%s)" -lt "$until" ]; do
    rows=$(compose ps -a --format '{{.Name}}|{{.State}}|{{.Health}}' api keycloak 2>/dev/null | grep '|' || true)
    now=$(echo "$rows" | awk -F'|' 'NF { printf "%s%s: %s", (n++ ? ", " : ""), $1, ($3 != "" ? $3 : $2) }')
    if [ -n "$now" ] && [ "$now" != "$last" ]; then echo "  $now"; last=$now; fi
    if [ "$(echo "$rows" | grep -c '|')" -ge 2 ] && ! echo "$rows" | awk -F'|' '$3 != "healthy"' | grep -q .; then return 0; fi
    if echo "$rows" | awk -F'|' '$2 == "exited" || $2 == "dead"' | grep -q .; then
      echo "A core container stopped; see ./eax.sh logs api (or keycloak)."; return 1
    fi
    sleep 5
  done
  echo "The API or sign-in was not ready after 15 minutes; see ./eax.sh logs api (or keycloak)."
  return 1
}
# --wait-all: waits until every part is up (the API's start-up status, D255): Reports, Documents, Diagrams, the sample data
wait_all() {
  local until=$(( $(date +%s) + 1800 )) t0 last="" now
  t0=$(date +%s)
  echo "Waiting for everything: Reports, Documents, Diagrams and the sample data (up to 30 minutes)..."
  while [ "$(date +%s)" -lt "$until" ]; do
    now=$(compose exec -T api python -c "import json,urllib.request as u; d=json.load(u.urlopen('http://localhost:8000/api/startup',timeout=20)); print(d['overall']+'|'+', '.join(p['key']+': '+p['status'] for p in d['parts']))" 2>/dev/null | tail -n1 || true)
    if [ -n "$now" ] && [ "$now" != "$last" ]; then echo "  ${now#*|}"; last=$now; fi
    case "$now" in
      up\|*) echo "Everything is up after $(( $(date +%s) - t0 )) s."; return 0 ;;
      down\|*) if ! echo "$now" | grep -q starting; then echo "Started, but not everything is up (see above): ./eax.sh logs <service>."; return 0; fi ;;
    esac
    sleep 10
  done
  echo "Not everything was up after 30 minutes (see above); EA Explorer is usable, the rest may still come."
}
# start-later: the second tier, the rest without touching the core, then the switched-off ones created
start_later() {
  tiers
  if [ -n "${LATER// }" ]; then
    echo "Starting after the core (D255):$LATER"
    # shellcheck disable=SC2086
    compose up -d --build --no-deps $LATER || true
  fi
  if [ -n "${OFF// }" ]; then
    # shellcheck disable=SC2086
    compose create --build $OFF || true
    # shellcheck disable=SC2086
    compose stop $OFF >/dev/null 2>&1 || true
  fi
  echo "Everything is started."
}
up_services() {
  local t0
  write_services_file
  if [ "$#" -gt 0 ]; then
    case " $* " in *" api "*) compose up -d --build --scale "api=$(api_servers)" "$@" ;; *) compose up -d --build "$@" ;; esac
    return
  fi
  tiers
  [ -n "${OFF// }" ] && echo "Switched off (D191):$OFF: created, not started."
  echo "Starting the core first (D255):$FIRST"
  # shellcheck disable=SC2086
  compose up -d --build --scale "api=$(api_servers)" $FIRST || return 1
  echo "Waiting for the API and sign-in to be ready (the database upgrade and the built-in models come first)..."
  t0=$(date +%s)
  if wait_core; then READY=$(( $(date +%s) - t0 )); else READY=""; fi
  if [ -n "$WAIT_ALL" ]; then        # --wait-all: the rest now, in this terminal, and wait until everything is up
    start_later
    wait_all
    return 0
  fi
  # the second tier in the background, with its own log, so this terminal is free at once
  nohup "$BASH" "$0" start-later >/dev/null 2>&1 &
  echo "Reports, documents, draw.io, backups and the operations helper start now in the background (log: work/logs/eax-*-start-later.log)."
  echo "(To wait for everything instead: ./eax.sh up --wait-all.)"
  if [ -n "$READY" ]; then
    echo "EA Explorer is ready after ${READY} s: you can sign in."
    echo "Still starting in the background: Reports, Documents, Diagrams and the sample data; the screens show each in red, amber or green (down, starting, up)."
    if [ ! -f "$WORK_DIR/.check-hint-shown" ]; then   # the first start: how to check it (D582)
      echo "Check your installation: System admin > Self-test > Smoke test > Start (it prepares what it needs);"
      echo "  or ./eax.sh test (smoke) or ./eax.sh test full."
      echo "  Results: Self-test > History and the report. Steps: docs/deployment.md, \"Check your installation\"."
      : > "$WORK_DIR/.check-hint-shown" 2>/dev/null || true
    fi
  fi
}
show_services() {
  local n
  for n in $SERVICE_NAMES; do
    printf '%-11s %-4s %s=%s   containers: %s\n' "$n" "$(service_on "$n" && echo on || echo off)" "$(service_setting "$n")" \
      "$(setting "$(service_setting "$n")" on)" "$(service_containers "$n")"
  done
  run_compose ps -a
}
set_service() {
  local n="${1:-}" v="${2:-}" key copy
  key=$(service_setting "$n") || { err "unknown service '$n'. One of: $SERVICE_NAMES"; exit 1; }
  case "$v" in on|off) ;; *) err "say on or off: ./eax.sh service $n on"; exit 1 ;; esac
  mkdir -p "$WORK_DIR/config-history"
  copy="eaexplorer.env.$(date -u +%Y%m%d-%H%M%S).$(echo "${USER:-eax}" | tr -c 'A-Za-z0-9_.\n-' '-').$n-$v"
  cp -p "$ENV_FILE" "$WORK_DIR/config-history/$copy"
  if grep -qE "^[[:space:]]*$key[[:space:]]*=" "$ENV_FILE"; then
    sed -i.bak -E "s|^[[:space:]]*$key[[:space:]]*=.*|$key=$v|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '\n%s=%s\n' "$key" "$v" >> "$ENV_FILE"
  fi
  [ "$n" = mcp ] && { sed -i.bak -E '/^[[:space:]]*EAX_MCP_ENABLED[[:space:]]*=/d' "$ENV_FILE" && rm -f "$ENV_FILE.bak"; }
  write_services_file
  echo "$key=$v written (the config file before is kept as $WORK_DIR/config-history/$copy)."
  # shellcheck disable=SC2046
  if [ "$(service_containers "$n")" = api ]; then run_compose restart api
  elif [ "$v" = on ]; then run_compose up -d $(service_containers "$n")
  else run_compose stop $(service_containers "$n"); fi
}

# ------------------------------------------------------------------ output helpers
show_urls() {
  local H P S
  H=$(setting EAX_HOSTNAME localhost); P=$(setting EAX_HTTPS_PORT 443)
  S=$([ "$P" = "443" ] && echo "" || echo ":$P")
  echo "Start page:  https://$H$S/"
  echo "Swagger:     https://$H$S/api/docs"
  if service_on reports; then echo "Reports:     https://reports.$H$S/"; fi
  if service_on documents; then echo "Documents:   https://docs.$H$S/"; fi
  echo "Keycloak:    https://$H$S/auth/admin/"
  if service_on mcp; then echo "MCP server:  https://$H$S/mcp"; fi
  if [ "$(setting EAX_HTTP_API_MCP false)" = "true" ]; then
    local HP; HP=$(setting EAX_HTTP_PORT 80); [ "$HP" = "80" ] && HP="" || HP=":$HP"
    echo "Also on plain http (this computer only): http://localhost$HP/api/docs and http://localhost$HP/mcp"
  fi
  show_templates_hint
  return 0
}
# one-time admin task (phase 13, D262): the TOGAF template deliverables are bought or downloaded from The Open Group
# (publication I094) and kept in the library folder, never in git; shown until the folder has them
show_templates_hint() {
  local dir togaf
  dir=$(setting EAX_LIBRARY_DIR ./library); togaf="$dir/templates/togaf"
  if [ -d "$togaf" ] && find "$togaf" -type f \( -name '*.docx' -o -name '*.doc' -o -name '*.pptx' -o -name '*.xlsx' \) | grep -q .; then
    return 0
  fi
  echo
  echo "One-time admin task: the TOGAF template deliverables (for architecture projects)"
  echo "  1. Download 'The TOGAF Standard, 10th Edition - Template Deliverables' (The Open Group publication I094):"
  echo "     https://publications.opengroup.org/i094"
  echo "  2. Unzip it into $togaf, keeping its phase folders (the files stay on this computer; git ignores them)."
  echo "     To use another folder, set EAX_LIBRARY_DIR in $ENV_FILE (it must hold templates/togaf) and run ./eax.sh up."
  echo "  3. As a Super Admin: Administration > Project library > Load templates from the folder."
}

# ------------------------------------------------------------------ the local certificate (D107)
ca_path() {
  local d; d=$(setting EAX_TLS_DIR ./work/data/tls)
  case "$d" in */*) echo "$d/ca.crt" ;; *) echo "" ;; esac
}
trust() {
  local ca; ca=$(ca_path)
  [ -n "$ca" ] || { err "EAX_TLS_DIR is a Docker volume; copy ca.crt out with: docker compose cp setup:/tls/ca.crt ."; exit 1; }
  if [ "${1:-}" = "--remove" ]; then
    if [ "$(uname)" = Darwin ]; then
      while security delete-certificate -c "EA Explorer local CA" ~/Library/Keychains/login.keychain-db >/dev/null 2>&1; do :; done
      echo "Removed EA Explorer certificates from your login keychain."
    else
      echo "Run: sudo rm -f /usr/local/share/ca-certificates/eaexplorer-local-ca.crt && sudo update-ca-certificates --fresh"
    fi
    return 0
  fi
  [ -f "$ca" ] || { err "no $ca yet: run ./eax.sh up first (the setup service makes it)."; exit 1; }
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
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Library" "eax_library" "$(setting EAX_LIBRARY_DB_PASSWORD)" "database eaxlibrary"
  printf '%-34s %-14s %-16s %s\n' "PostgreSQL Views" "eax_views" "$(setting EAX_VIEWS_DB_PASSWORD)" "database eaxviews"
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
             "user_global_architect|eax-user|Architect on every model" \
             "user_project_admin|eax-user|Project Admin of the sample architecture project (runs its setup and people)" \
             "user_lead_architect|eax-user|Lead Architect of the sample architecture project" \
             "user_stakeholder|eax-user|Stakeholder of the sample architecture project (reads; approves documents in 13.1)"; do
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
    case "$a" in --all) all=true ;; --yes|-y) yes=true ;; --certificate) cert=true ;; *) err "unknown option $a"; exit 1 ;; esac
  done
  echo "This deletes everything in $(pwd)/$WORK_DIR: the config file, all logs, the laptop data folders, and every backup and"
  echo "restore log (work/backups)."
  $all && echo "With --all it also deletes the Docker volumes: the databases and documents start empty."
  if ! $yes; then
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing deleted."; exit 0; }
  fi
  # the logs first, where no reset deletes them (R2.30); a log backup never stops the cleanup
  "$BASH" ./eaxpy.sh logs backup before-cleanup --outside-work || echo "The logs could not be backed up first."
  if [ -f "$ENV_FILE" ]; then
    if $all; then compose down -v --remove-orphans || true; else compose down --remove-orphans || true; fi
  elif $all; then
    echo "No $ENV_FILE, so the Docker volumes cannot be found by name; remove them with: docker volume ls"
  fi
  if $cert; then
    # work/tools (uv and its Python, for eaxpy.sh, D331) is kept either way
    find "${WORK_DIR:?}" -mindepth 1 -maxdepth 1 ! -name tools -exec rm -rf {} + 2>/dev/null || true
    echo "The work folder is empty. Run ./eax.sh init laptop to start again."
  else
    # keep work/data/tls: the local certificate you trusted with ./eax.sh trust (D107)
    find "${WORK_DIR:?}" -mindepth 1 -maxdepth 1 ! -name data ! -name tools -exec rm -rf {} + 2>/dev/null || true
    [ -d "$WORK_DIR/data" ] && find "$WORK_DIR/data" -mindepth 1 -maxdepth 1 ! -name tls -exec rm -rf {} + 2>/dev/null || true
  fi
  # backups and restore logs are written by the containers (as root on Linux): if any are left, a container removes them
  if [ -d "$WORK_DIR/backups" ] || [ -d "$WORK_DIR/data/backups" ]; then
    docker run --rm -v "$(pwd)/$WORK_DIR:/w" --entrypoint sh "${EAX_IMAGE_POSTGRES:-postgres:17-alpine}" -c 'rm -rf /w/backups /w/data/backups' \
      >/dev/null 2>&1 || true
  fi
  if [ -d "$WORK_DIR/backups" ]; then
    warn "WARNING: $WORK_DIR/backups could not be deleted completely: delete it by hand (sudo rm -rf $WORK_DIR/backups)."
  else
    echo "Every backup and restore log is deleted."
  fi
  if $cert; then :
  else
    echo "The work folder is empty apart from the local certificate (work/data/tls). Run ./eax.sh init laptop to start again."
  fi
}

# Backups and restores from the command line (D227) need the database, the backup container and the operations helper
backup_helpers() { compose up -d db backup ops >/dev/null; }

# Stops early with a plain message when the Docker engine is not reachable
assert_docker() {
  if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
    err "Docker is not running (or still starting). Start Docker Desktop or the Docker service, check with: docker version (it must show a Server section), then run this again."
    exit 1
  fi
}

# the console (phase 13.5, D330): a numbered menu for getting a system that is down back up. It runs in the operations
# helper (services/ops/console.py); what needs this machine (start, stop, diagnostics, any eax command) it hands back
# here by its exit code. No sign-in: being on the machine is the trust. With --server: another installation, its API.
console() {
  local self="./$(basename "${BASH_SOURCE[0]}")" code stopped="" line ver
  if [[ " $* " == *" --server "* ]]; then
    assert_docker; compose run --rm --no-deps api python -m eax.console_cli remote "$@"; return
  fi
  ver=$(sed -n 's/^version = "\(.*\)"/\1/p' services/api/version.toml)
  while true; do
    code=99
    if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 && [ -f "$ENV_FILE" ] && [ -z "$stopped" ]; then
      # built first: an ops image from before the console has no console.py (a rebuild takes seconds when nothing changed)
      echo "Starting the console (the operations helper; the first time it is built, a minute)..."
      if compose up -d --build --no-deps ops >/dev/null 2>&1; then
        set +e; compose exec ops python3 /app/console.py --version "$ver"; code=$?; set -e
        case "$code" in 0|20|21|23|25) ;; *)   # it failed: the basic menu, not the same failure again
          echo "The console stopped with an error (exit $code); the basic menu follows. Its log: work/logs/console-*.log"; code=99 ;; esac
      fi
    fi
    if [ "$code" = 99 ]; then      # the helper could not start: only what this machine can do
      echo
      if [ -n "$stopped" ]; then echo "EA Explorer console (basic: everything is stopped)"
      else echo "EA Explorer console (basic: the operations helper is not running)"; fi
      docker info >/dev/null 2>&1 || echo "Docker is not running: start it, then choose 1."
      [ -f "$ENV_FILE" ] || echo "Not set up yet: there is no $ENV_FILE. Run ./eax.sh init laptop first."
      echo "  1  Start everything"; echo "  2  Save a diagnostics file for support"
      echo "  c  Command prompt (every eax command)"; echo "  q  Quit"
      read -r -p "Choose: " line || line=q
      case "$line" in 1) code=20 ;; 2) code=23 ;; c) code=25 ;; q) code=0 ;; *) code=98 ;; esac
    fi
    case "$code" in
      0) return ;;
      20) stopped=""; "$BASH" "$self" up || true ;;
      21) "$BASH" "$self" down || true; stopped=1 ;;
      23) "$BASH" "$self" diag || true ;;
      25) echo "Type an eax command (for example: logs api, services, backups). Empty or back: the menu."
          while read -r -p "eax> " line; do
            case "$line" in ""|back|b|menu) break ;; console*) echo "You are in the console already."; continue ;; esac
            # shellcheck disable=SC2086
            "$BASH" "$self" $line || true
          done ;;
    esac
  done
}

# did you mean (R2.29): the same rule as eaxcli/help.py suggest() and unknown()
unknown_command() {
  LC_ALL=C awk -v orig="$1" -v word="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" '
    function dist(a, b,   i, j, la, lb, p, c, x, y, z) {
      la = length(a); lb = length(b)
      for (j = 0; j <= lb; j++) p[j] = j
      for (i = 1; i <= la; i++) {
        c[0] = i
        for (j = 1; j <= lb; j++) {
          x = p[j] + 1; y = c[j - 1] + 1; z = p[j - 1] + (substr(a, i, 1) != substr(b, j, 1))
          c[j] = (x < y ? (x < z ? x : z) : (y < z ? y : z))
        }
        for (j = 0; j <= lb; j++) p[j] = c[j]
      }
      return p[lb]
    }
    /^### / { split(substr($2, 1), nm, "|"); for (k in nm) seen[nm[k]] = 1 }
    END {
      most = (length(word) <= 3) ? 1 : 2; n = 0
      for (name in seen) {
        s = (length(word) >= 2 && index(name, word) == 1) ? 0 : dist(word, name)
        if (s <= most) { n++; key[n] = sprintf("%d %s", s, name) }
      }
      for (i = 2; i <= n; i++) { v = key[i]; for (j = i - 1; j >= 1 && key[j] > v; j--) key[j + 1] = key[j]; key[j + 1] = v }
      out = ""; for (i = 1; i <= n && i <= 3; i++) { sub(/^[0-9]+ /, "", key[i]); out = out (i > 1 ? ", " : "") key[i] }
      hint = (out != "") ? " Did you mean: " out "?" : ""
      printf "unknown command '\''%s'\''.%s Run ./eax.sh help, or ./eax.sh menu to pick one.", orig, hint
    }' eaxcli/help.txt
}

# ------------------------------------------------------------------ commands
# eax test --reset-survival: settings outlive a real reset (D561), one Python program for every form
if [ "$CMD" = "test" ]; then case " $* " in *" --reset-survival "*) exec "$BASH" ./eaxpy.sh "$@" ;; esac; fi
case "$CMD" in
  help|-h|--help|/\?) show_help "${2:-}" "${3:-}"; exit $? ;;
  document)       shift; document "$@"; exit 0 ;;
  logs) case "${2:-}" in backup|clean) exec "$BASH" ./eaxpy.sh "$@" ;; esac ;;   # back up and clean the logs (R2.30)
esac
case "$CMD" in
  menu) EAX_FORM=sh exec "$BASH" ./eaxpy.sh menu ;;   # the numbered menu (R2.29), one Python program for every form
  deploy|secrets|packs|schedule|persist)   # packs (D546); schedule: scheduled commands (D559); persist (R2.26)
    # phase 36 (D498, D504): one Python program for every form (D500): eaxpy.sh fetches uv and Python into work/tools
    exec "$BASH" ./eaxpy.sh "$@" ;;
  restart)
    # down, then up: each as its own run of this script (own log); the data is kept
    for step in "down" "up${WAIT_ALL:+ --wait-all}"; do
      echo; echo "=== ./eax.sh $step"
      # shellcheck disable=SC2086
      "$BASH" "./$(basename "${BASH_SOURCE[0]}")" $step || { err "./eax.sh $step failed; restart stopped there."; exit 1; }
    done
    exit 0 ;;
  console)        shift; console "$@"; exit 0 ;;
  cleanup)        shift; cleanup "$@"; exit 0 ;;
  clean-run|clean-debug|clean-restart)
    # cleanup --all --yes, init, then up or debug: each as its own run of this script (own log);
    # clean-restart brings the running containers down first
    kind="${2:-laptop}"; last=up; [ "$CMD" = clean-debug ] && last=debug
    steps=("cleanup --all --yes" "init $kind" "$last${WAIT_ALL:+ --wait-all}")
    if [ "$CMD" = clean-restart ]; then
      if [ -f "$ENV_FILE" ]; then steps=("down" "${steps[@]}")
      else echo "No $ENV_FILE yet: nothing running to bring down; going straight to clean-run."; fi
    fi
    for step in "${steps[@]}"; do
      echo; echo "=== ./eax.sh $step"
      # shellcheck disable=SC2086
      "$BASH" "./$(basename "${BASH_SOURCE[0]}")" $step || { err "./eax.sh $step failed; $CMD stopped there."; exit 1; }
    done
    exit 0 ;;
esac

start_log "$@"
if [ -f eaexplorer.env ] && [ ! -f "$ENV_FILE" ]; then
  echo "Found eaexplorer.env in the main folder: it is no longer used. The config now lives in $ENV_FILE."
  echo "Delete the old file and run ./eax.sh init laptop (or copy your changes into $ENV_FILE)."
fi

case "$CMD" in check|up|start-later|debug|status|logs|down|backup|backups|footprint|restore|restores|restore-log|delete-backup|delete-restore|app-backup|restore-model|restore-app|stop-backup|services|service|import|update|rollback) assert_docker ;; esac

case "$CMD" in
  init)
    K="${2:-laptop}"
    [ -f "$ENV_FILE" ] && { err "$ENV_FILE already exists; not overwriting. Use ./eax.sh cleanup to start again."; exit 1; }
    [ -f "deploy/templates/eaexplorer.$K.env" ] || { err "unknown deployment kind: $K"; exit 1; }
    mkdir -p work/logs work/backups work/proxy work/data/imports work/data/exports work/data/tls
    # Plain copy with LF endings: no passwords are generated
    tr -d '\r' < "deploy/templates/eaexplorer.$K.env" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Created $ENV_FILE ($K) from deploy/templates/eaexplorer.$K.env."
    if [ "$K" = "laptop" ]; then show_logins
    else
      # a server or platform keeps its backups in a mounted folder (R2.44, D635): no backups until it is set
      if [ -t 0 ]; then
        read -r -p "Folder for backups: a mounted network share or volume (empty: set EAX_BACKUP_DIR later): " BDIR
        if [ -n "$BDIR" ]; then
          sed -i "s|^EAX_BACKUP_DIR=\$|EAX_BACKUP_DIR=$BDIR|" "$ENV_FILE" && echo "Backups go to $BDIR (EAX_BACKUP_DIR)."
        else echo "No backups are taken until EAX_BACKUP_DIR is set in $ENV_FILE."; fi
      else echo "Set EAX_BACKUP_DIR in $ENV_FILE to the mounted folder for backups: no backups are taken until it is set."; fi
      echo "Now replace every change-me value in $ENV_FILE with your own passwords before ./eax.sh up."
    fi
    ;;
  check)
    docker version --format 'Docker {{.Server.Version}}' || { err "Docker is not running."; exit 1; }
    docker compose version
    [ -f "$ENV_FILE" ] || { err "no $ENV_FILE yet: run ./eax.sh init"; exit 1; }
    echo "Config: $ENV_FILE ($(kind))"
    run_compose config --quiet && echo "Compose configuration is valid."
    ;;
  up)
    shift
    # the industry packs first (D584): new or changed files from the pack sources; quick when nothing changed; never fatal
    if [ "$#" -eq 0 ]; then "$BASH" ./eaxpy.sh packs auto || true; fi
    # an upgrade (D230): while a running installation is rebuilt, the proxy shows the maintenance page
    PAGE=""
    if [ "$#" -eq 0 ] && [ ! -f work/proxy/maintenance ] && [ -n "$(compose ps --status running -q proxy 2>/dev/null)" ]; then
      mkdir -p work/proxy; echo upgrade > work/proxy/maintenance; PAGE=1
      echo "Everyone sees the maintenance page until this has finished."
    fi
    if ! up_services "$@"; then
      if [ -n "$PAGE" ]; then rm -f work/proxy/maintenance; fi
      echo "docker compose failed. Collecting diagnostics..."; diagnostics
      err "docker compose failed. Full log with diagnostics: $LOG"; exit 1
    fi
    if [ -n "$PAGE" ]; then rm -f work/proxy/maintenance; fi
    if [ "$#" -gt 0 ]; then show_part_urls "$@"; else show_urls; show_logins; fi
    ;;
  start-later) start_later ;;
  debug)
    shift
    if [ "$#" -eq 0 ]; then "$BASH" ./eaxpy.sh packs auto || true; fi        # the industry packs first (D584)
    if ! up_services "$@"; then echo "docker compose up failed; recording what is running anyway."; fi
    diagnostics
    if [ "$#" -gt 0 ]; then show_part_urls "$@"; else show_urls; show_logins; fi
    watch_containers "$@"
    ;;
  diag)    diagnostics ;;
  status)  heading "EA Explorer $(release), build $(build_id)"
           _ps=$(compose ps -a) || { echo "docker compose failed. Collecting diagnostics..."; diagnostics; err "docker compose failed. Full log with diagnostics: $LOG"; exit 1; }
           printf '%s\n' "$_ps" | colour_status; show_filesystems ;;
  logs)    shift; compose logs -f --tail=100 "$@" || true ;;
  down)    run_compose down ;;
  backup)  service_on backups || { err "backups are switched off: ./eax.sh service backups on"; exit 1; }
           shift; backup_helpers; compose exec ops python3 /app/ops.py backup "$@" ;;
  backups) shift; backup_helpers; compose exec ops python3 /app/ops.py list "$@" ;;
  footprint) shift; compose exec ops python3 /app/ops.py footprint "$@" ;;   # how much each container takes (R2.22)
  stop-backup) backup_helpers; compose exec ops python3 /app/ops.py stop-backup ;;
  restore-app) shift; compose exec api python -m eax.backups_cli restore-all "$@" ;;
  maintenance)
    case "${2:-}" in
      on) mkdir -p work/proxy; echo maintenance > work/proxy/maintenance
          echo "The maintenance page is shown to everyone until: ./eax.sh maintenance off" ;;
      off) rm -f work/proxy/maintenance; echo "The maintenance page is off." ;;
      *) echo "Usage: ./eax.sh maintenance on|off"; exit 2 ;;
    esac ;;
  restore) service_on backups || { err "backups are switched off: ./eax.sh service backups on"; exit 1; }
           shift; VER=$(sed -n 's/^version = "\(.*\)"/\1/p' services/api/version.toml)
           backup_helpers; compose exec ops python3 /app/ops.py restore "$@" --version "$VER" ;;
  restores) backup_helpers; compose exec ops python3 /app/ops.py restores ;;
  databases) compose exec api python -m eax.databases "$@" ;;              # where each database lives (R2.50)
  restore-log|delete-backup|delete-restore) C="$1"; shift; backup_helpers; compose exec ops python3 /app/ops.py "$C" "$@" ;;
  app-backup) shift; compose exec api python -m eax.backups_cli backup "$@" ;;
  import) shift; compose exec api python -m eax.deliveries_cli "$@" ;;
  update) shift; backup_helpers; compose exec ops python3 /app/ops.py update "$@" ;;      # updates (phase 36, D417)
  rollback) shift; backup_helpers; compose exec ops python3 /app/ops.py rollback "$@" ;;
  restore-model) shift; compose exec api python -m eax.backups_cli restore "$@" ;;
  test) shift                                                              # the self-test (phase 36.1, D367, D529)
        case " $* " in *" --build "*)                                          # only build the runner image (D570)
          echo "Building the test runner (about 1.5 GB, 5 to 15 minutes the first time): base image, Python packages, Chromium, scanners."
          compose --profile test build testrunner && echo "The test runner is built."; exit $? ;;
        esac
        if [ "${1:-}" = "clean" ]; then shift                                 # delete every test run's data (R2.0.1, D593)
          compose exec api python -m eax.testing.cli clean all "$@"; exit $?
        fi
        if [ "${1:-}" = "delete" ]; then shift                                # delete test results for good (R2.43)
          compose exec api python -m eax.testing.cli delete "$@"; exit $?
        fi
        READ=""
        for a in "$@"; do case "$a" in --status|--last|--report|--fixtures|--clean) READ="${a#--}" ;; esac; done
        if [ -n "$READ" ]; then
          REST=""; for a in "$@"; do [ "$a" = "--$READ" ] || REST="$REST $a"; done
          # shellcheck disable=SC2086
          compose exec api python -m eax.testing.cli "$READ" $REST
        else
          echo "Preparing the test runner... (the first time about 5 to 15 minutes; seconds when it is current)"   # D584
          compose --profile test build testrunner || { err "the test runner could not be built."; exit 1; }
          VER=$(sed -n 's/^version = "\(.*\)"/\1/p' services/api/version.toml)
          backup_helpers; compose exec ops python3 /app/ops.py test "$@" --version "$VER"
        fi ;;
  standby)                                                                 # the database standby (phase 36.3, D527)
    case "${2:-status}" in
      status) compose exec db psql -U postgres -c "SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication"
              compose exec db-standby psql -U postgres -c "SELECT pg_is_in_recovery() AS following_the_primary, now() - pg_last_xact_replay_timestamp() AS behind_by" ;;
      promote) echo "The standby becomes the primary: it stops following and accepts changes. Then set EAX_DB_HOST=db-standby (or the standby's host) and run ./eax.sh up."
               printf "Type PROMOTE to go on: "; read -r ans; [ "$ans" = "PROMOTE" ] || { echo "Nothing changed."; exit 1; }
               compose exec -u postgres db-standby pg_ctl promote -D /var/lib/postgresql/data ;;
      *) echo "Usage: ./eax.sh standby status|promote"; exit 2 ;;
    esac ;;
  services) show_services ;;
  service) set_service "${2:-}" "${3:-}" ;;
  servers)
    if [ -z "${2:-}" ]; then echo "API and job servers wanted: $(api_servers) (EAX_API_SERVERS). Running:"; compose ps api
    else
      case "$2" in ''|*[!0-9]*) echo "Usage: ./eax.sh servers <1 to 16>"; exit 1 ;; esac
      if [ "$2" -lt 1 ] || [ "$2" -gt 16 ]; then echo "Usage: ./eax.sh servers <1 to 16>"; exit 1; fi
      mkdir -p "$WORK_DIR/config-history"
      cp -p "$ENV_FILE" "$WORK_DIR/config-history/eaexplorer.env.$(date -u +%Y%m%d-%H%M%S).${USER:-console}.servers-$2"
      if grep -qE '^\s*EAX_API_SERVERS\s*=' "$ENV_FILE"; then sed -i.bak -E "s/^\s*EAX_API_SERVERS\s*=.*/EAX_API_SERVERS=$2/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
      else printf '\n# ---- API and job servers (D249)\nEAX_API_SERVERS=%s\n' "$2" >> "$ENV_FILE"; fi
      echo "Running $2 API and job server(s); stopping a server lets the jobs it runs finish first."
      compose up -d --no-deps --no-recreate --scale "api=$2" api
    fi ;;
  url)     show_urls; show_logins ;;
  logins)  [ -f "$ENV_FILE" ] || { err "no $ENV_FILE yet: run ./eax.sh init first."; exit 1; }; show_logins ;;
  trust)   [ -f "$ENV_FILE" ] || { err "no $ENV_FILE yet: run ./eax.sh init first."; exit 1; }; trust "${2:-}" ;;
  *)       err "$(unknown_command "$CMD")"; exit 1 ;;
esac
echo "Log: $LOG"
