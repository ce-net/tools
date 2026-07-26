#!/usr/bin/env python3
"""One-shot migration: point every ceapp's capauth call sites at the shared module.

Before: each app carried a hand-edited `capauth.py` whose env var and posture were baked
into the file body. After: one canonical `capauth.py` (vendored, byte-identical everywhere)
plus a call site that names the app's own env var and default.

It also FIXES A REAL BUG the copies hid. Several apps were copied from a sibling and kept
the sibling's env var: ce-apps, ce-doors and ce-track-demo all read CE_TRACK_AUTH, and six
apps read CE_GRIDCONV_AUTH. Hardening one silently changed the posture of the others, and
the copied apps had no variable of their own at all. Each app gets its own here.

Run from the workspace root. Idempotent.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# repo -> (env var, default posture). Derived from what each app's own capauth.py read,
# except where the copied-sibling bug meant the app had no variable of its own.
APPS = {
    "ce-46elks": ("CE_ELKS_AUTH", "capiam"),
    "ce-agents-state": ("CE_AGENTSTATE_AUTH", "allow"),
    "ce-aggregator": ("CE_SENSOR_AUTH", "capiam"),
    "ce-analyst-state": ("CE_ANSTATE_AUTH", "allow"),
    "ce-analyst": ("CE_ANALYST_AUTH", "allow"),
    "ce-apps": ("CE_APPS_AUTH", "allow"),                 # was CE_TRACK_AUTH (copied)
    "ce-arduino": ("CE_SENSOR_AUTH", "capiam"),
    "ce-blobs": ("CE_BLOBS_AUTH", "allow"),               # was CE_GRIDCONV_AUTH (copied)
    "ce-building-api": ("CE_SENSOR_AUTH", "capiam"),
    "ce-city-state": ("CE_CITYSTATE_AUTH", "allow"),
    "ce-city": ("CE_CITY_AUTH", "allow"),
    "ce-devices-state": ("CE_DEVSTATE_AUTH", "allow"),
    "ce-devices": ("CE_DEVICES_AUTH", "allow"),
    "ce-doors": ("CE_DOORS_AUTH", "allow"),               # was CE_TRACK_AUTH (copied)
    "ce-grid-ai": ("CE_GRIDAI_AUTH", "allow"),
    "ce-grid-convert-embed": ("CE_GRIDCONV_AUTH", "allow"),
    "ce-grid-convert-text": ("CE_GRIDCONV_AUTH", "allow"),
    "ce-inbox": ("CE_INBOX_AUTH", "allow"),
    "ce-index-state": ("CE_INDEXSTATE_AUTH", "allow"),
    "ce-index": ("CE_INDEX_AUTH", "allow"),
    "ce-localfs": ("CE_LOCALFS_AUTH", "allow"),           # was CE_GRIDCONV_AUTH (copied)
    "ce-map-state": ("CE_MAPSTATE_AUTH", "allow"),
    "ce-map": ("CE_MAP_AUTH", "allow"),
    "ce-org-state": ("CE_ORGSTATE_AUTH", "allow"),
    "ce-org": ("CE_ORG_AUTH", "allow"),
    "ce-pages-state": ("CE_PAGESTATE_AUTH", "allow"),
    "ce-pages": ("CE_PAGES_AUTH", "allow"),
    "ce-power-feed": ("CE_POWERFEED_AUTH", "allow"),
    "ce-power-state": ("CE_POWERSTATE_AUTH", "allow"),
    "ce-power": ("CE_POWER_AUTH", "allow"),
    "ce-search": ("CE_SEARCH_AUTH", "allow"),
    "ce-seat-state": ("CE_SEATSTATE_AUTH", "allow"),
    "ce-sensor-camera": ("CE_SENSOR_AUTH", "capiam"),
    "ce-sensor-climate": ("CE_SENSOR_AUTH", "capiam"),
    "ce-sensor-led": ("CE_SENSOR_AUTH", "capiam"),
    "ce-sentinel-state": ("CE_SENTINEL_STATE_AUTH", "allow"),
    "ce-sentinel": ("CE_SENTINEL_AUTH", "allow"),
    "ce-staff": ("CE_STAFF_AUTH", "allow"),
    "ce-stream": ("CE_STREAM_AUTH", "allow"),             # was CE_GRIDCONV_AUTH (copied)
    "ce-tasks": ("CE_TASKS_AUTH", "allow"),
    "ce-track-demo": ("CE_TRACKDEMO_AUTH", "allow"),      # was CE_TRACK_AUTH (copied)
    "ce-track-state": ("CE_TRACKSTATE_AUTH", "allow"),
    "ce-track": ("CE_TRACK_AUTH", "allow"),
    "clip-state": ("CE_CLIPSTATE_AUTH", "allow"),
    "ocean-doc": ("CE_OCEANDOC_AUTH", "allow"),           # was CE_GRIDCONV_AUTH (copied)
    "ocean-state": ("CE_OCEANSTATE_AUTH", "allow"),
    "ocean": ("CE_OCEAN_AUTH", "allow"),
}

# Repos whose app-specific helpers moved to an app-local `appcap.py`.
APPCAP = {
    "ce-agents": [(r"\bcapauth\.from_env\(\)", "appcap.from_env()"),
                  (r"\bcapauth\.self_issue\(", "appcap.self_issue("),
                  (r"\bcapauth\.mint\(", "appcap.mint_for_agent("),
                  (r"\bcapauth\.WALLET_LABEL\b", "appcap.WALLET_LABEL")],
    "ce-files": [(r"\bcapauth\.from_env\(\)", "appcap.from_env()"),
                 (r"\bcapauth\.self_issue_drive\(", "appcap.self_issue_drive("),
                 (r"\bcapauth\.self_issue\(", "appcap.self_issue("),
                 (r"\bcapauth\.WALLET_LABEL\b", "appcap.WALLET_LABEL")],
    "ce-pg": [(r"\bcapauth\.from_env\(\)", "appcap.from_env()"),
              (r"\bcapauth\.self_issue\(", "appcap.self_issue("),
              (r"\bcapauth\.WALLET_LABEL\b", "appcap.WALLET_LABEL")],
    "ce-books": [(r"\bcapauth\.ensure_pg_token\(", "appcap.ensure_pg_token("),
                 (r"\bcapauth\.authorizer_from_env\(\)", "appcap.from_env()")],
}


def py_files(repo: str):
    d = os.path.join(ROOT, repo)
    for name in sorted(os.listdir(d)):
        if name.endswith(".py") and name not in ("capauth.py", "ce.py", "appcap.py"):
            yield os.path.join(d, name)


def migrate(repo: str, env_var: str, default: str) -> int:
    """Point this repo's call sites at the shared module, naming its own env var."""
    arg = f'"{env_var}"' + (f', default="{default}"' if default != "allow" else "")
    changed = 0
    for path in py_files(repo):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        out = src
        # `capauth.authorizer_from_env()` -> `capauth.authorizer_from_env("CE_X_AUTH")`
        out = re.sub(r"capauth\.authorizer_from_env\(\s*\)",
                     f"capauth.authorizer_from_env({arg})", out)
        # bare `authorizer_from_env()` (imported by name)
        out = re.sub(r"(?<!\.)\bauthorizer_from_env\(\s*\)",
                     f"authorizer_from_env({arg})", out)
        if out != src:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
            changed += 1
    return changed


def migrate_appcap(repo: str) -> int:
    changed = 0
    for path in py_files(repo):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        out = src
        for pattern, repl in APPCAP[repo]:
            out = re.sub(pattern, repl, out)
        if out != src:
            # make sure appcap is imported wherever it is now referenced
            if "appcap." in out and not re.search(r"^\s*import appcap", out, re.M):
                out = re.sub(r"^(import capauth.*)$", r"\1\nimport appcap", out,
                             count=1, flags=re.M)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
            changed += 1
    return changed


def main() -> int:
    total = 0
    for repo, (var, default) in sorted(APPS.items()):
        if not os.path.isdir(os.path.join(ROOT, repo)):
            print(f"skip {repo} (absent)")
            continue
        n = migrate(repo, var, default)
        total += n
        if n:
            print(f"{repo:<24} {var:<26} default={default:<7} {n} file(s)")
    for repo in sorted(APPCAP):
        if os.path.isdir(os.path.join(ROOT, repo)):
            n = migrate_appcap(repo)
            total += n
            print(f"{repo:<24} -> appcap.py                              {n} file(s)")
    print(f"\n{total} files updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
