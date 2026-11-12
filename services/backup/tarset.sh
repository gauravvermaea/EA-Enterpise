#!/bin/sh
# tarset NAME FOLDER ARCHIVE [tar options...]: one file set of an infrastructure backup (backup.sh), so a failure says
# which set and which files (R2.46; owner, 12 Nov 2026: an on-demand backup said only "tar: error exit delayed from
# previous errors"). A file that changed while it was read is kept as read (a warning, exit 1 of GNU tar); a file that
# could not be read at all fails the backup with tar's own lines about it (exit 2), the last line naming the set.
tarset() {
  name=$1 dir=$2 archive=$3
  shift 3
  err="$archive.err"
  if tar -C "$dir" "$@" -czf "$archive" . 2>"$err"; then rc=0; else rc=$?; fi
  if [ "$rc" -eq 0 ]; then
    rm -f "$err"
    return 0
  fi
  if [ "$rc" -eq 1 ]; then
    echo "backup: files $name: warning, some files changed while they were read (kept as read):"
    grep -v 'error exit delayed' "$err" | head -5 | sed 's/^/  /'
    rm -f "$err"
    return 0
  fi
  echo "backup: files $name failed (tar exit $rc):" >&2
  grep -v 'error exit delayed' "$err" | head -10 | sed 's/^/  /' >&2
  why=$(grep -v 'error exit delayed' "$err" | head -3 | sed 's/^tar: //' | tr '\n' ';' | sed 's/;$//; s/;/; /g')
  rm -f "$err" "$archive"
  echo "files $name ($dir) could not be read: ${why:-tar exit $rc}" >&2
  return "$rc"
}
