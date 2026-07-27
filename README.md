# tools — EMPTY, ON PURPOSE

**There are no tools. Every capability is a ce app.**

A script in this directory runs on one machine, for one person, with no discovery, no
capability gate, and no way for an agent or another device to call it. The same development
environment has to work across thousands of devices on different operating systems. That is
impossible with scripts and ordinary with apps.

`ce` is the one door: `ce app install` makes an app a command, `ce app run --on node=` runs it
elsewhere, and agents reach the same ops through ce-mcp and `describe`.

## Where everything went

| was | now |
|---|---|
| `ocean`, `backlog`, `oceanlib.py` | the **ocean** app: `ocean`, `ocean backlog` |
| `ce-build`, `ce-dev-link`, `remote-test.sh`, `remote-test-all.sh` | the **ce-build** app (`ce.build`) — builds on any node, no ssh |
| `ce-app-publish` | the **ce-publish** app |
| `claude-md-guard` | the **ce-lint** app |
| `ce-vendor` | dies with `[script].deps`; its drift check belongs to ce-lint |
| the eight `*-to-ocean` migrations, `migrate-capauth.py`, `ce-rootsync-init.sh` | deleted — one-shots, already run |

This directory stays only for its license files. Do not add anything to it.
