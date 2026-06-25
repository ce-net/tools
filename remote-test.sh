#!/usr/bin/env bash
#
# remote-test.sh — build & test a ce-net Rust app on the Hetzner relay box, not locally.
#
# WHY: the dev laptop is a 4-core machine with a chronically-full disk shared by many
# agents; local `cargo test` thrashes the disk to ENOSPC and corrupts the shared target
# cache. The Hetzner relay (178.105.145.170) has 51 GB free disk and a real Linux
# x86_64 toolchain, so heavy compilation belongs there. This script is the dev tool for
# that: it rsyncs an app plus its path-dependencies to /opt/build/ on Hetzner and runs
# `cargo test` (and optionally clippy) there, serialized under a global build lock so
# concurrent invocations (and the 4 GB / no-swap RAM limit) don't OOM the box.
#
# USAGE:
#   tools/remote-test.sh <app>              # rsync + cargo test on Hetzner, stream tail
#   tools/remote-test.sh <app> --clippy     # also run clippy --all-targets
#   tools/remote-test.sh <app> --no-sync    # skip rsync (reuse what's already on Hetzner)
#   tools/remote-test.sh <app> --jobs N     # cargo -j N (default 2; use 1 for heavy crates)
#   tools/remote-test.sh <app> --build-only # cargo build instead of test (faster smoke)
#
# OUTPUT: prints the tail of the build/test log and a final line:
#   REMOTE-TEST <app>: PASS   (exit 0)
#   REMOTE-TEST <app>: FAIL   (exit non-zero)
# Full log is saved on Hetzner at /opt/build/logs/<app>.log and locally to
#   tools/.remote-logs/<app>.log
#
# This is intentionally a plain script so any agent/human can use it immediately. It can
# later be folded into `rdev` (rdev test <app> --on hetzner) once the mesh exec path is
# mature; the convention here (/opt/build/<repo> siblings, per-app target dir, flock) is
# the same one already used by /opt/build/build.sh.
set -uo pipefail

HOST="${CE_REMOTE_HOST:-root@178.105.145.170}"
KEY="${CE_REMOTE_KEY:-$HOME/.ssh/id_ed25519}"
LOCAL_ROOT="${CE_LOCAL_ROOT:-$HOME/ce-net}"
REMOTE_ROOT="/opt/build"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -i "$KEY")

APP=""
DO_CLIPPY=0
DO_SYNC=1
JOBS=2
MODE="test"
while [ $# -gt 0 ]; do
  case "$1" in
    --clippy) DO_CLIPPY=1 ;;
    --no-sync) DO_SYNC=0 ;;
    --jobs) shift; JOBS="$1" ;;
    --build-only) MODE="build" ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) APP="$1" ;;
  esac
  shift
done
[ -n "$APP" ] || { echo "usage: remote-test.sh <app> [--clippy] [--no-sync] [--jobs N] [--build-only]" >&2; exit 2; }
[ -d "$LOCAL_ROOT/$APP" ] || { echo "no such app dir: $LOCAL_ROOT/$APP" >&2; exit 2; }

# Path-dependency repos that must exist as siblings under /opt/build for path = "../x" to resolve.
# Always sync ce + ce-rs (transitive); then auto-discover every other ../<sibling> path-dep.
DEPS=(ce ce-rs)
while IFS= read -r dep; do
  [ -n "$dep" ] || continue
  case " ${DEPS[*]} " in *" $dep "*) ;; *) [ -d "$LOCAL_ROOT/$dep" ] && DEPS+=("$dep") ;; esac
done < <(grep -oE 'path *= *"\.\./[a-zA-Z0-9_.-]+' "$LOCAL_ROOT/$APP/Cargo.toml" 2>/dev/null | sed -E 's#.*\.\./##')

run_ssh() {
  local tries=0
  while :; do
    ssh "${SSH_OPTS[@]}" "$HOST" "$@" && return 0
    tries=$((tries+1)); [ $tries -ge 5 ] && return 1
    echo "  ssh attempt $tries failed (likely MaxStartups); retrying in $((tries*5))s..." >&2
    sleep $((tries*5))
  done
}

rsync_dir() {
  local d="$1" tries=0
  while :; do
    rsync -az --delete \
      --exclude target --exclude .git --exclude node_modules --exclude dist \
      -e "ssh ${SSH_OPTS[*]}" "$LOCAL_ROOT/$d/" "$HOST:$REMOTE_ROOT/$d/" && return 0
    tries=$((tries+1)); [ $tries -ge 5 ] && return 1
    echo "  rsync $d attempt $tries failed; retrying in $((tries*5))s..." >&2
    sleep $((tries*5))
  done
}

if [ "$DO_SYNC" = 1 ]; then
  echo "==> syncing ${DEPS[*]} $APP -> $HOST:$REMOTE_ROOT/"
  for d in "${DEPS[@]}" "$APP"; do
    rsync_dir "$d" || { echo "rsync failed for $d" >&2; exit 3; }
  done
fi

CLIPPY_CMD=":"
[ "$DO_CLIPPY" = 1 ] && CLIPPY_CMD="nice -n 19 cargo clippy --all-targets -j$JOBS"
CARGO_CMD="nice -n 19 cargo $MODE -j$JOBS"

echo "==> remote $MODE on $HOST (target-$APP, -j$JOBS$([ "$DO_CLIPPY" = 1 ] && echo ', +clippy'))"
mkdir -p "$LOCAL_ROOT/tools/.remote-logs"

# Serialize heavy builds across invocations with flock; per-app target dir keeps incremental caches.
REMOTE_SCRIPT="
set -o pipefail
source \$HOME/.cargo/env
mkdir -p $REMOTE_ROOT/logs
cd $REMOTE_ROOT/$APP || exit 9
export CARGO_TARGET_DIR=$REMOTE_ROOT/target-$APP
export CARGO_NET_RETRY=5
exec 9>$REMOTE_ROOT/.buildlock
flock -w 2400 9 || { echo 'could not acquire build lock'; exit 8; }
{
  echo \"=== \$(date -u) remote $MODE $APP ===\"
  rustc --version
  $CLIPPY_CMD && $CARGO_CMD
} 2>&1 | tee $REMOTE_ROOT/logs/$APP.log
"

run_ssh "$REMOTE_SCRIPT" | tee "$LOCAL_ROOT/tools/.remote-logs/$APP.log"
# Determine pass/fail from the remote log tail (tee above shows it live).
if run_ssh "grep -qE 'test result: ok|Finished .(test|release|dev). profile' $REMOTE_ROOT/logs/$APP.log && ! grep -qE 'error\\[|error:|test result: FAILED|panicked|could not compile' $REMOTE_ROOT/logs/$APP.log"; then
  echo "REMOTE-TEST $APP: PASS"
  exit 0
else
  echo "REMOTE-TEST $APP: FAIL"
  exit 1
fi
