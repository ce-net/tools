#!/usr/bin/env bash
#
# remote-test-all.sh — run `cargo test` for many ce-net apps on the Hetzner box and
# print a consolidated PASS/FAIL tally. Thin loop over tools/remote-test.sh (which
# serializes via flock and uses per-app target dirs). Safe to run while other builds
# happen on Hetzner — it just queues on the lock.
#
# USAGE:
#   tools/remote-test-all.sh                 # default: all 13 Rust apps
#   tools/remote-test-all.sh ce-iam ce-db    # specific apps
#   APPS_EXTRA_ARGS="--jobs 1" tools/remote-test-all.sh ce-query   # pass-through flags
#
# Per-app logs: tools/.remote-logs/<app>.log ; tally printed at the end.
set -uo pipefail
cd "$(dirname "$0")/.."

DEFAULT_APPS=(ce-iam ce-storage ce-pubsub ce-db ce-query ce-fn ce-notes ce-mail ce-cdn ce-pin ce-gke ce-meet ce-drive)
APPS=("$@")
[ ${#APPS[@]} -eq 0 ] && APPS=("${DEFAULT_APPS[@]}")

declare -a SUMMARY
rc_all=0
for app in "${APPS[@]}"; do
  echo "############################################################"
  echo "## remote cargo test: $app"
  echo "############################################################"
  if tools/remote-test.sh "$app" ${APPS_EXTRA_ARGS:-} >/dev/null 2>&1; then
    # re-run quietly already done; grab the test counts from the log
    counts=$(grep -hoE 'test result: ok\. [0-9]+ passed' "tools/.remote-logs/$app.log" 2>/dev/null | grep -oE '[0-9]+' | awk '{s+=$1} END{print s+0}')
    SUMMARY+=("PASS  $app  (${counts} tests)")
    echo ">> $app PASS (${counts} tests)"
  else
    fails=$(grep -hoE 'test result: FAILED|error\[|could not compile|signal: 9' "tools/.remote-logs/$app.log" 2>/dev/null | head -1)
    SUMMARY+=("FAIL  $app  (${fails:-see log})")
    echo ">> $app FAIL"
    rc_all=1
  fi
done

echo
echo "================= REMOTE CARGO TEST TALLY (Hetzner) ================="
for line in "${SUMMARY[@]}"; do echo "  $line"; done
echo "===================================================================="
exit $rc_all
