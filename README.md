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
