#!/bin/sh
# Where each database lives (R2.50, D611): own_servers prints "<database> <host> <port>" for every database whose
# setting puts it on a server of its own (not the shared one, $PGHOST:$PGPORT). backup.sh dumps those from there and
# restore.sh puts them back there; the rest are on the shared server. Each server is reached as postgres with the
# superuser password, as the library's and the views' have been (D410).
#   EA Explorer's own (connection strings):  EAX_<CHANGELOG|PROJECTS|TESTS|OPERATIONS|PERSONAL|LIBRARY_MODELS|ARCHIVE|FILES|FARM>_DB_URL
#   the services' (hosts):                   EAX_<LIBRARY|VIEWS|KEYCLOAK|SUPERSET|MAYAN>_DB_HOST (and _PORT)
url_part() {   # url_part <url> host|port|db
  _rest=${1#*://}; _rest=${_rest#*@}; _hp=${_rest%%/*}; _db=${_rest#*/}; _db=${_db%%\?*}
  case "$2" in
    host) echo "${_hp%%:*}";;
    port) case "$_hp" in *:*) echo "${_hp##*:}";; *) echo 5432;; esac;;
    db) echo "$_db";;
  esac
}
own_servers() {
  for KIND in CHANGELOG PROJECTS TESTS OPERATIONS PERSONAL LIBRARY_MODELS ARCHIVE FILES FARM; do
    eval U=\${EAX_${KIND}_DB_URL:-}
    [ -n "$U" ] || continue
    H=$(url_part "$U" host); P=$(url_part "$U" port); N=$(url_part "$U" db)
    [ -n "$H" ] && [ -n "$N" ] || continue
    [ "$H:$P" = "$PGHOST:$PGPORT" ] && continue
    echo "$N $H $P"
  done
  for PAIR in "LIBRARY ${EAX_LIBRARY_DB_NAME:-eaxlibrary}" "VIEWS ${EAX_VIEWS_DB_NAME:-eaxviews}" "KEYCLOAK keycloak" \
              "SUPERSET superset" "MAYAN mayan"; do
    KIND=${PAIR%% *} N=${PAIR#* }
    eval H=\${EAX_${KIND}_DB_HOST:-\$PGHOST} P=\${EAX_${KIND}_DB_PORT:-\$PGPORT}
    [ -n "$H" ] || H=$PGHOST
    [ "$H:$P" = "$PGHOST:$PGPORT" ] && continue
    echo "$N $H $P"
  done | sort -u
}
