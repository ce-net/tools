# Working in Ocean — the short version for agents

Since 2026-07-26 the workspace's work lives in Ocean, not in markdown on Leif's laptop.
`FINDINGS.md`, `AGENTS.md`, `PLAN/` and `notes/` are tombstones.

## Every session starts here

    tools/backlog                          # pending work: Started first, then Todo

Claim what you take, so nobody duplicates you:

    tools/backlog start <id> --by Vigil

File anything you trip over that is not your current task:

    tools/backlog add "ce app has no way to restart a local daemon" \
        --why "install leaves the old process running, so you silently test the old code" \
        --where "ce-appmgr" --by Vigil

Close it with what actually fixed it — `--how` is required on purpose:

    tools/backlog done <id> --how "added ce app daemon restart; kill-by-pid was the workaround"

Other verbs: `show <id>`, `search <text>`, `drop <id> --why "..."`, `list --all`.

## The shape

Org **Rydenfalk**:

| project | holds |
|---|---|
| **Backlog** | Todo / Started / Completed. An item's state IS its folder. |
| **Log** | Agent log (coordination) + Investigations (long-form write-ups) |
| **Plans** | workstream design docs |
| **Notes** | working notes and session write-ups |
| **Directives** | Leif's words, verbatim. The law. |
| one per system | e.g. **Sentinel** |

## Two rules that matter more than the rest

**Link relevant things together.** `[[Wiki Link]]` a backlog item to the plan, directive or
log entry it belongs with. Backlinks are how the next agent finds context you already paid
for. A `[[name]]` that does not resolve yet marks something worth writing, not an error.

**Never create a duplicate.** Everything writes through `oceanlib.Ocean.ensure_doc`, which
matches on (parent, normalized title) against an index built from ONE `doc.tree` call. If
you write your own tool, use it — do not call `doc.create` directly.

There is a matching trap: dedup by title means two *distinct* items that produce the same
title would silently merge and one would be lost. Pass `distinct_key=` when you know the
items are distinct (a migration, where every source line is its own item) and the second one
gets a suffixed title instead of vanishing. This is not hypothetical — the first migration
run collapsed 272 agent entries into 93 documents before it was caught.

## The tools

| tool | what |
|---|---|
| `tools/backlog` | the day-to-day CLI |
| `tools/oceanlib.py` | shared client: dedup index, retrying calls, `ensure_doc` |
| `tools/workspace-to-ocean` | the one-time migration; idempotent, safe to re-run |
| `tools/directives-to-ocean` | publishes `directives/` into Ocean + ce-drive |
| `tools/sentinel-to-ocean` | publishes the ce-sentinel docs |

Ocean's latency is spiky — `doc.list` takes seconds and individual calls occasionally stall
for a minute and then answer instantly. `oceanlib` retries with backoff rather than failing a
long run on one slow reply. It is on the backlog.
