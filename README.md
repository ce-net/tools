# tools — DEPRECATED, and nearly empty

**There is no tools directory.** Every tool is a ce app, or a verb of the app it serves.
A script in one person's workspace runs on one laptop. A ce app runs on any node, from any
device, through the mesh — which is what development here has to be.

Read `directives/dev-environment.md` in the workspace for the law and the reasoning. The plan
lives in Ocean: *Removing tools — every tool is a ce app, one door to the mesh*.

## Where the tools went

| was | now |
|---|---|
| `ocean`, `backlog` | verbs of the **ocean** app: `ocean`, `ocean backlog` |
| `oceanlib.py` | `ocean/workspace.py` |
| `workspace-to-ocean`, `directives-to-ocean`, `index-to-ocean`, `log-to-items`, `repo-docs-to-ocean`, `sentinel-to-ocean`, `ocean-doc-ce-pg`, `ocean-doc-workspace` | deleted — one-shot migrations, already run |
| `migrate-capauth.py` | deleted — one-shot, already run |
| `ce-app-publish` | the **ce-publish** app |
| `remote-test.sh`, `remote-test-all.sh` | superseded by `ce-build` |
| `ce-rootsync-init.sh` | deleted — one-shot, already run |
| `ce-vendor` | `ce-py/tools/ce-vendor` — it vendors ce-py's modules, and it dies when `[script].deps` lands |
| `claude-md-guard` | `ce-lint/claude-md-guard` — ce-lint is the enforcement arm |

## What is left, and why it is still here

`ce-build` and `ce-dev-link` build Rust repos on a remote node. They are the last two, and they
are the hardest, because the work has to happen ON the target machine. They become one **ce-build
app** that answers on the mesh, so any device can ask any node to build.

Until then they stay here, deprecated. Do not add anything to this directory.
