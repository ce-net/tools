# ce-net dev tools

Small dev tools shared by all agents/humans working in this workspace.

## remote-test.sh — build & test a Rust app on Hetzner, not locally

The dev laptop is a 4-core machine whose disk is chronically full and shared by many
concurrent agents. Running `cargo test` locally thrashes the single shared
`.cargo-shared` target to **ENOSPC**, which corrupts the build cache for *every* agent.
The Hetzner relay box (`178.105.145.170`) has **51 GB free disk** and a real Linux
x86_64 toolchain, so heavy compilation belongs there.

`remote-test.sh` rsyncs an app plus its path-dependency repos (`ce`, `ce-rs`, and
`ce-coord` when needed) to `/opt/build/<repo>/` on Hetzner and runs `cargo test` there,
serialized under a global `flock` so concurrent invocations don't OOM the box (4 GB RAM,
**no swap**). Each app gets its own `CARGO_TARGET_DIR=/opt/build/target-<app>` so
incremental caches are preserved and apps don't fight over one target lock.

### Usage

```bash
tools/remote-test.sh <app>              # rsync + cargo test on Hetzner
tools/remote-test.sh <app> --clippy     # also clippy --all-targets
tools/remote-test.sh <app> --no-sync    # reuse what's already on Hetzner (skip rsync)
tools/remote-test.sh <app> --jobs 1     # cargo -j1 (use for RAM-heavy crates, e.g. datafusion)
tools/remote-test.sh <app> --build-only # cargo build smoke instead of full test
```

It prints the tail of the log and a final verdict line:

```
REMOTE-TEST <app>: PASS    # exit 0
REMOTE-TEST <app>: FAIL    # exit 1
```

Full logs: on Hetzner at `/opt/build/logs/<app>.log`, locally at
`tools/.remote-logs/<app>.log`.

### Notes / gotchas

- **Never run `cargo test`/`cargo build` for these apps on the laptop** — use this script.
- `cargo` on Hetzner is installed via rustup at `~/.cargo/bin` and is **not** in the
  non-login SSH `PATH`; the script sources `~/.cargo/env`.
- SSH sometimes returns "Connection closed by … port 22" when many agents connect at
  once (sshd `MaxStartups`). The script retries with backoff.
- If a remote build is killed with `signal: 9` / OOM, re-run with `--jobs 1`.
- Env overrides: `CE_REMOTE_HOST`, `CE_REMOTE_KEY`, `CE_LOCAL_ROOT`.
- Hetzner also runs the production `ce-relay` service. Builds use `nice -n 19` and `-j2`
  to stay out of the relay's way; keep it that way.

### Future

This is a plain script so it's usable immediately. It can later be folded into `rdev`
(`rdev test <app> --on hetzner`) once the mesh exec/sync path is mature — the convention
here (`/opt/build/<repo>` siblings, per-app target dir, flock) matches the existing
`/opt/build/build.sh`.

## claude-md-guard — keep the root context file an index, not an archive

The workspace root `CLAUDE.md` is loaded into every agent's context on every session. It once
reached 159 KB (~40k tokens per agent per session) because every new verbatim directive was
pasted into it in full, restating laws earlier entries had already set.

The guard enforces the split that fixed it:

- a byte budget (24 KB) on `CLAUDE.md`,
- no verbatim quote blocks in it — those belong in `directives/<theme>.md`,
- every theme file linked from `CLAUDE.md`, and listed in `directives/README.md`.

    ./claude-md-guard            # check; exit 1 with the fix on violation
    ./claude-md-guard --stats    # sizes only

Wire it as the workspace repo's `pre-commit` hook:

    printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/tools/claude-md-guard"\n' \
      > ../.git/hooks/pre-commit && chmod +x ../.git/hooks/pre-commit

Raising the budget is not the fix. Moving content out is: repo descriptions to `REPOS.md`,
machines/ports/release to `OPERATIONS.md`, how-to into the skills, design into `PLAN/`.

## directives-to-ocean — publish the directive archive onto the mesh

Reads `directives/*.md` and publishes each directive as its own **Ocean** document (org
Rydenfalk, project Directives, nested under a doc per theme, plus an index doc) and as markdown
in **ce-drive** under `/directives/<theme>/`. Idempotent: a second run updates the documents it
already created rather than duplicating them.

    ./directives-to-ocean               # both faces
    ./directives-to-ocean --dry-run     # show what it would write
    ./directives-to-ocean --index-only  # rebuild just the index document
    ./directives-to-ocean --drive-only | --ocean-only

Why: the archive should be reachable from the mesh — `ce.ocean` `search`/`doc.tree` for agents
and humans, `ce.files` for AI — not only from one laptop's context file. Run it after recording
a new directive.

## ocean — read and restructure the Ocean workspace

`backlog` covers the work loop. `ocean` covers everything else, so that reshaping the
workspace stops meaning "write a throwaway python script that imports oceanlib".

    tools/ocean                          # the whole tree, teamspace by teamspace
    tools/ocean tree Projects            # one teamspace, in full
    tools/ocean find <text>              # search every document
    tools/ocean read <id>                # a document's markdown
    tools/ocean new Projects "Alice"     # a page in a teamspace (or under a page id)
    tools/ocean mv <id> Projects         # re-file a page
    tools/ocean rm <id>                  # to the trash (recoverable)
    tools/ocean teamspace new|rm <name>

Ids may be given by their first 8 characters, the ones every listing prints.

Two things it does that a hand-written script will not. Every write **re-reads the server
to see whether it landed** before retrying — Ocean's replies time out long before its
writes do, so a blind retry is how you end up with two of something. And `teamspace rm`
refuses a teamspace that still holds pages, because `project.delete` trashes everything
inside it and that should never be a surprise.

Ocean answers slowly when this laptop is loaded (load hit 980 on 2026-07-26 and every mesh
call returned 504). Commands retry with backoff and are safe to re-run; if one prints
FAILED, run it again rather than reaching for the raw op.
