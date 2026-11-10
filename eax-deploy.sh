#!/usr/bin/env bash
# EA Explorer installer for Linux and macOS (phase 36, D502). Needs nothing but this file: it asks for the repository
# link and the version, downloads EA Explorer from there (the release archive with curl, no git needed; a shallow
# clone when git is here), checks it, and then runs its deployment wizard (./eax.sh deploy).
#
#   curl -fsSL <repository's raw address>/eax-deploy.sh -o eax-deploy.sh && bash eax-deploy.sh
#
# Options (each is asked when not given):
#   --repo URL          the repository link (the public git URL EA Explorer comes from)
#   --channel C         prod (release tags vX.Y.Z), rc (vX.Y.Z-rc.N) or latest (the main branch)
#   --version REF       a tag, branch or commit (instead of choosing from the channel)
#   --folder DIR        where to put it (default ~/eaexplorer)
#   --no-deploy         download and check only; run ./eax.sh deploy yourself later
# Anything after -- is passed to the wizard (e.g. -- --web, -- --console --kind server).
set -euo pipefail

REPO="${EAX_REPO:-}"; CHANNEL=""; REF=""; FOLDER="${EAX_FOLDER:-$HOME/eaexplorer}"; DEPLOY=1; PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --channel) CHANNEL="$2"; shift 2 ;;
    --version) REF="$2"; shift 2 ;;
    --folder) FOLDER="$2"; shift 2 ;;
    --no-deploy) DEPLOY=0; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --) shift; PASS=("$@"); break ;;
    *) echo "Unknown option $1 (--help lists them)"; exit 2 ;;
  esac
done

ask() {   # ask "question" default -> the answer
  local a
  read -r -p "$1${2:+ [$2]}: " a </dev/tty || a=""
  printf '%s' "${a:-$2}"
}
say() { printf '%s\n' "$*"; }

say "EA Explorer installer: downloads EA Explorer and starts its deployment wizard."
[ -n "$REPO" ] || REPO=$(ask "Repository link" "https://github.com/gauravvermaea/EA-Enterpise")
[ -n "$REPO" ] || { say "A repository link is needed."; exit 2; }
REPO="${REPO%/}"; REPO="${REPO%.git}"

if [ -z "$REF" ]; then
  if [ -z "$CHANNEL" ]; then
    say "Which channel?"
    say "  1  Prod     released versions (tags vX.Y.Z)   [default]"
    say "  2  RC       release candidates (vX.Y.Z-rc.N), for testing before a release"
    say "  3  Latest   the newest commit of main, for trying what is being built (not for production)"
    case "$(ask "Choose" 1)" in 2|rc) CHANNEL=rc ;; 3|latest) CHANNEL=latest ;; *) CHANNEL=prod ;; esac
  fi
  if [ "$CHANNEL" = latest ]; then
    REF=main
  else
    # the tags: git ls-remote when git is here, otherwise GitHub's API (other hosts: --version)
    tags=""
    if command -v git >/dev/null 2>&1 && [ -z "${EAX_NO_GIT:-}" ]; then
      tags=$(git ls-remote --tags --refs "$REPO" 2>/dev/null | sed 's#.*refs/tags/##' || true)
    elif [[ "$REPO" =~ github\.com[/:]([^/]+)/([^/]+)$ ]]; then
      tags=$(curl -fsSL "https://api.github.com/repos/${BASH_REMATCH[1]}/${BASH_REMATCH[2]}/tags?per_page=100" 2>/dev/null \
             | grep -o '"name": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/' || true)
    fi
    if [ "$CHANNEL" = rc ]; then pat='^v[0-9]+\.[0-9]+\.[0-9]+-rc\.[0-9]+$'; else pat='^v[0-9]+\.[0-9]+\.[0-9]+$'; fi
    list=$(printf '%s\n' "$tags" | grep -E "$pat" | sort -V -r | head -10 || true)
    if [ -n "$list" ]; then
      say "Versions on $CHANNEL (newest first):"; i=0
      while IFS= read -r t; do i=$((i + 1)); say "  $i  $t"; done <<< "$list"
      pick=$(ask "Choose (or type a tag)" 1)
      if [[ "$pick" =~ ^[0-9]+$ ]]; then REF=$(printf '%s\n' "$list" | sed -n "${pick}p"); else REF="$pick"; fi
    else
      say "No $CHANNEL versions could be listed (no git here, or not GitHub)."
      REF=$(ask "Type the version (a tag such as v0.19.0, or a branch)" "$([ "$CHANNEL" = rc ] && echo rc || echo release)")
    fi
  fi
fi
[ -n "$REF" ] || { say "A version is needed."; exit 2; }
CHANNEL="${CHANNEL:-$(case "$REF" in *-rc.*) echo rc ;; v[0-9]*) echo prod ;; *) echo latest ;; esac)}"

if [ -e "$FOLDER" ] && [ -n "$(ls -A "$FOLDER" 2>/dev/null)" ]; then
  if [ -f "$FOLDER/eax.sh" ]; then
    say "$FOLDER holds EA Explorer already. To move it to a newer version use its updates (./eax.sh update);"
    say "to deploy it again: cd $FOLDER && ./eax.sh deploy"
  else
    say "$FOLDER is not empty: choose another folder with --folder."
  fi
  exit 1
fi
mkdir -p "$FOLDER"

# the address of the release archive (GitHub, GitLab; EAX_ARCHIVE_URL for anything else, e.g. https://host/{repo}/{ref}.tar.gz)
archive_url() {
  if [ -n "${EAX_ARCHIVE_URL:-}" ]; then printf '%s' "${EAX_ARCHIVE_URL//\{repo\}/$REPO}" | sed "s#{ref}#$REF#g"; return; fi
  if [[ "$REPO" =~ ^(https?://|git@)github\.com[/:]([^/]+)/([^/]+)$ ]]; then
    o="${BASH_REMATCH[2]}"; n="${BASH_REMATCH[3]}"
    if [[ "$REF" =~ ^[0-9a-f]{7,40}$ ]]; then printf 'https://github.com/%s/%s/archive/%s.tar.gz' "$o" "$n" "$REF"
    elif [[ "$REF" =~ ^v[0-9] ]]; then printf 'https://github.com/%s/%s/archive/refs/tags/%s.tar.gz' "$o" "$n" "$REF"
    else printf 'https://github.com/%s/%s/archive/refs/heads/%s.tar.gz' "$o" "$n" "$REF"; fi
  elif [[ "$REPO" =~ ^(https?://|git@)gitlab\.com[/:]([^/]+)/([^/]+)$ ]]; then
    printf 'https://gitlab.com/%s/%s/-/archive/%s/%s-%s.tar.gz' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "$REF" "${BASH_REMATCH[3]}" "$REF"
  fi
}

say "Downloading EA Explorer $REF from $REPO into $FOLDER ..."
if command -v git >/dev/null 2>&1 && [ -z "${EAX_NO_GIT:-}" ] && [ -z "${EAX_ARCHIVE_URL:-}" ]; then
  METHOD="git clone --depth 1"
  git clone --quiet --depth 1 --branch "$REF" "$REPO" "$FOLDER" 2>/dev/null || {
    # a commit is not a branch: fetch that one commit
    git -C "$FOLDER" init -q && git -C "$FOLDER" remote add origin "$REPO" && git -C "$FOLDER" fetch -q --depth 1 origin "$REF" \
      && git -C "$FOLDER" checkout -q FETCH_HEAD; }
else
  URL=$(archive_url)
  [ -n "$URL" ] || { say "Without git only GitHub and GitLab addresses can be downloaded (or set EAX_ARCHIVE_URL)."; rmdir "$FOLDER" 2>/dev/null || true; exit 1; }
  METHOD="archive $URL"
  tmp=$(mktemp)
  curl -fsSL "$URL" -o "$tmp" || { say "Could not download $URL"; rm -f "$tmp"; rmdir "$FOLDER" 2>/dev/null || true; exit 1; }
  tar -xzf "$tmp" -C "$FOLDER" --strip-components=1
  rm -f "$tmp"
fi

# the check: is this EA Explorer?
for f in eax.sh eaxpy.sh docker-compose.yml eaxcli/deploy.py services/api/version.toml deploy/templates/eaexplorer.server.env; do
  [ -f "$FOLDER/$f" ] || { say "The download does not look like EA Explorer ($f is missing): check the link and the version."; exit 1; }
done
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$FOLDER/services/api/version.toml" | head -1)
chmod +x "$FOLDER/eax.sh" "$FOLDER/eaxpy.sh" "$FOLDER/eax-deploy.sh" 2>/dev/null || true
mkdir -p "$FOLDER/work"
cat > "$FOLDER/work/install.json" <<EOF
{"repo": "$REPO", "channel": "$CHANNEL", "ref": "$REF", "version": "$VERSION", "method": "$METHOD", "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
say "EA Explorer $VERSION ($REF) is in $FOLDER."
if [ "$DEPLOY" = 1 ]; then
  cd "$FOLDER"
  exec bash ./eax.sh deploy ${PASS[@]+"${PASS[@]}"}
fi
say "Next: cd $FOLDER && ./eax.sh deploy"
