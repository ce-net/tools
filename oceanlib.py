"""Shared Ocean client for the workspace migration + backlog tools.

Ocean (github.com/ce-net/ocean) is where the workspace's work lives now: the backlog, the
agent log, the plans and the notes. These tools are the bridge that got them there and the
bridge agents use day to day.

THE ONE RULE THIS LIBRARY EXISTS TO ENFORCE: never create a duplicate. Every write goes
through :meth:`Ocean.ensure_doc`, which looks the title up in an index built from a single
``doc.tree`` call and updates in place if it is already there. Running any tool built on
this twice is a no-op, which is what makes migration safe to retry.

Ocean's latency is spiky (see FINDINGS), so every call retries with backoff rather than
failing a 400-document migration on one slow reply.
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ocean"))
import ce  # noqa: E402  (the ocean app's vendored SDK)

SERVICE = "ce.ocean"
CTL = "ocean/ctl"
ORG_NAME = "Rydenfalk"


def tables_to_lists(md: str) -> str:
    """Rewrite GFM tables as bullet lists, because Ocean's markdown has no table block.

    A pipe table sent to Ocean comes back as ONE run-on paragraph — every row and the
    `|---|---|` separator glued together — which is worse than useless in the doc that is
    supposed to explain the workspace. Repos keep real tables (GitHub renders them); the
    conversion happens here, at publish time, so the source stays correct markdown.

    `| a | b |` with header `| col | meaning |` becomes `- **a** — b`.
    """
    out, i = [], 0
    lines = md.split("\n")
    while i < len(lines):
        line = lines[i]
        is_row = line.strip().startswith("|") and line.strip().endswith("|")
        sep = (i + 1 < len(lines)
               and set(lines[i + 1].strip()) <= set("|-: ")
               and "-" in lines[i + 1])
        if not (is_row and sep):
            out.append(line)
            i += 1
            continue

        def cells(row):
            return [c.strip() for c in row.strip().strip("|").split("|")]

        headers = cells(line)
        i += 2  # skip the header and the |---| separator
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(cells(lines[i]))
            i += 1
        for r in rows:
            if not r:
                continue
            first, rest = r[0], [c for c in r[1:] if c]
            label = first.strip("*` ")
            if len(headers) > 2 and len(r) > 2:
                # Keep the column names when a row carries more than one value, or the
                # meaning of the second and third columns is lost.
                parts = [f"{headers[n]}: {r[n]}" for n in range(1, len(r)) if r[n]]
                out.append(f"- **{label}** — " + "; ".join(parts))
            elif rest:
                out.append(f"- **{label}** — {rest[0]}")
            else:
                out.append(f"- **{label}**")
        out.append("")
    return "\n".join(out)


def norm(title: str) -> str:
    """Titles are matched case-insensitively on collapsed whitespace, so a re-run that
    reflows a heading by one space does not create a second document."""
    return " ".join(str(title or "").split()).lower()


class OceanError(RuntimeError):
    pass


PROVIDER_CACHE = os.path.join(ROOT, ".ocean-provider")


class Ocean:
    def __init__(self, timeout_ms: int = 120000, verbose: bool = True):
        self.client = ce.connect()
        self.verbose = verbose
        self.provider = self._discover()
        self.timeout_ms = timeout_ms
        self._index: dict = {}      # (scope_id, norm(title)) -> doc id
        self._titles: dict = {}     # doc id -> title
        self._claimed: dict = {}    # scope -> {norm(title): distinct_key} — collision guard
        self.created = 0
        self.updated = 0
        self.skipped = 0

    # ----- discovery -----

    def _discover(self, tries: int = 3) -> str:
        """Find ce.ocean, surviving a laptop that is momentarily too loaded to answer.

        `find_service` blocks on the node's discovery path, which is the first thing to go
        when this machine is under load (a cargo build plus a dozen agents put it at load
        980 on 2026-07-26, and every workspace tool died on this one line before doing any
        work). Discovery is retried, and the last known provider is remembered on disk so a
        slow lookup costs a stale-but-correct id instead of the whole session's tooling. The
        cached id is only ever a FALLBACK: a real answer always wins and rewrites the cache.
        """
        last = None
        for attempt in range(tries):
            try:
                found = self.client.find_service(SERVICE)
            except Exception as e:  # noqa: BLE001 — a wedged lookup is not a missing service
                last = str(e)
                found = None
            if found:
                try:
                    with open(PROVIDER_CACHE, "w") as fh:
                        fh.write(found[0])
                except OSError:
                    pass
                return found[0]
            if attempt + 1 < tries:
                time.sleep(2 * (attempt + 1))
        cached = ""
        try:
            with open(PROVIDER_CACHE) as fh:
                cached = fh.read().strip()
        except OSError:
            pass
        if cached:
            if self.verbose:
                print(f"ocean: discovery unavailable ({last or 'no provider'}); "
                      f"using cached provider {cached[:12]}", file=sys.stderr)
            return cached
        raise OceanError(
            "ce.ocean is not reachable: discovery returned nothing and no provider is "
            f"cached in {PROVIDER_CACHE} ({last or 'install ocean-state + ocean'})")

    # ----- wire -----

    # Ops that CREATE something. Retrying one of these after a timeout is how you get two
    # documents from one item: the server did the work, the reply was just slow. Ocean's
    # latency is spiky enough that this is not theoretical — it produced a duplicate during
    # the 2026-07-26 migration. These are retried only through :meth:`create_doc`, which
    # checks whether the write actually landed before trying again.
    UNSAFE_TO_RETRY = ("doc.create", "org.create", "project.create", "doc.duplicate")

    def call(self, op, args=None, tries: int = 4):
        if op in self.UNSAFE_TO_RETRY:
            tries = 1
        last = None
        for attempt in range(tries):
            try:
                raw = self.client.request(
                    self.provider, CTL,
                    json.dumps({"op": op, "args": args or {}}),
                    timeout_ms=self.timeout_ms)
                reply = json.loads(raw.decode("utf-8") or "{}")
            except Exception as e:  # noqa: BLE001 — Ocean latency is spiky; retry reads
                last = str(e)
                if attempt + 1 < tries:
                    time.sleep(1.5 * (attempt + 1))
                continue
            if "error" in reply:
                raise OceanError(f"{op}: {reply['error']}")
            return reply.get("result")
        raise OceanError(f"{op}: no reply after {tries} tr{'y' if tries == 1 else 'ies'} ({last})")

    def create_doc(self, args: dict, scope: str, title: str, tries: int = 3) -> str:
        """Create a document, surviving a slow reply without creating it twice.

        On failure the write may or may not have landed, so we ASK before retrying: re-list
        the parent and adopt the document if it is already there. Only a confirmed absence
        justifies another create.
        """
        last = None
        for attempt in range(tries):
            try:
                return self.call("doc.create", args)["id"]
            except Exception as e:  # noqa: BLE001
                last = str(e)
                found = self._find_child(scope, title)
                if found:
                    return found
                time.sleep(1.5 * (attempt + 1))
        raise OceanError(f"doc.create({title!r}): {last}")

    def _find_child(self, scope: str, title: str):
        """Look for one title under one parent, straight from the server."""
        for op, key in (("doc.list", "parent"), ("doc.list", "project")):
            try:
                res = self.call(op, {key: scope})
            except Exception:  # noqa: BLE001
                continue
            for d in (res or {}).get("docs") or []:
                if norm(d.get("title")) == norm(title):
                    return d["id"]
        return None

    # ----- org / project -----

    def org(self) -> str:
        for o in self.call("org.list")["orgs"]:
            if (o.get("title") or o.get("name")) == ORG_NAME:
                return o["id"]
        return self.call("org.create", {"name": ORG_NAME})["id"]

    def ensure_project(self, org: str, name: str, visibility: str = "open") -> str:
        for p in self.call("project.list", {"org": org})["projects"]:
            if norm(p.get("title") or p.get("name")) == norm(name):
                return p["id"]
        pid = self.call("project.create",
                        {"org": org, "name": name, "visibility": visibility})["id"]
        if self.verbose:
            print(f"  + project {name}")
        return pid

    # ----- the dedup index -----

    def build_index(self):
        """One ``doc.tree`` call becomes the whole title index.

        The alternative — a ``doc.list`` per parent — is what makes a migration take an hour
        and hammer the one op that is already slow.
        """
        tree = self.call("doc.tree")
        self._index.clear()
        self._titles.clear()

        def walk(docs, scope):
            for d in docs:
                self._index[(scope, norm(d.get("title")))] = d["id"]
                self._titles[d["id"]] = d.get("title")
                kids = d.get("children")
                if isinstance(kids, list):
                    walk(kids, d["id"])

        for o in tree.get("tree", []):
            for pr in o.get("projects", []):
                walk(pr.get("docs", []), pr["id"])
        return len(self._index)

    def lookup(self, scope: str, title: str):
        return self._index.get((scope, norm(title)))

    def remember(self, scope: str, title: str, doc_id: str):
        self._index[(scope, norm(title))] = doc_id
        self._titles[doc_id] = title

    # ----- the only write path -----

    def ensure_doc(self, title, md, *, project=None, parent=None, icon=None,
                   update: bool = False, dry: bool = False, distinct_key=None):
        """Create the doc if absent; otherwise leave it alone (or update with update=True).

        ``distinct_key`` guards against SILENT MERGES. Dedup is by title, so two different
        source items that happen to produce the same title would collapse into one document
        and the second would be quietly dropped. When a caller knows the items are distinct
        (a migration, where every source line is its own item), it passes a stable key; on a
        collision the title is suffixed with it instead of merging. Stable input gives a
        stable suffix, so re-running is still idempotent.

        Returns (doc_id, "created" | "updated" | "exists").
        """
        scope = parent or project
        if scope is None:
            raise OceanError("ensure_doc needs a project or a parent")
        if distinct_key is not None:
            claimed = self._claimed.setdefault(scope, {})
            prior = claimed.get(norm(title))
            if prior is not None and prior != distinct_key:
                title = f"{title} · {distinct_key}"
            else:
                claimed[norm(title)] = distinct_key
        existing = self.lookup(scope, title)
        if existing:
            if not update:
                self.skipped += 1
                return existing, "exists"
            if not dry:
                self.call("doc.update", {"doc": existing, "title": title,
                                         "md": tables_to_lists(md),
                                         **({"icon": icon} if icon else {})})
            self.updated += 1
            return existing, "updated"
        if dry:
            self.created += 1
            return "(dry)", "created"
        args = {"title": title, "md": tables_to_lists(md)}
        args["parent" if parent else "project"] = parent or project
        if icon:
            args["icon"] = icon
        doc_id = self.create_doc(args, scope, title)
        self.remember(scope, title, doc_id)
        self.created += 1
        return doc_id, "created"

    def move(self, doc_id: str, parent: str):
        return self.call("doc.move", {"doc": doc_id, "parent": parent})

    def summary(self) -> str:
        return (f"{self.created} created, {self.updated} updated, "
                f"{self.skipped} already there")


def title_from(text: str, fallback: str, limit: int = 110, split_dash: bool = False) -> str:
    """A stable, readable one-line title from a chunk of prose.

    Stability matters more than beauty: the title IS the dedup key, so it must come out the
    same on every run over the same source text.

    ``split_dash`` cuts at the first em dash, which is right for a FINDINGS bullet
    (`description — where — why`) and catastrophically wrong for a log heading
    (`2026-07-24 (Compass) — SHIPPED: ...`), where it collapses every entry by one agent on
    one day to the same title. That mistake would have merged 179 of 272 agent entries into
    93 documents on the first migration run — hence the flag, defaulting to off.
    """
    line = " ".join(str(text or "").split())
    if not line:
        return fallback
    if split_dash:
        for sep in (" — ", " -- "):
            if sep in line[:limit]:
                line = line.split(sep)[0]
                break
    if len(line) > limit:
        cut = line[:limit].rsplit(" ", 1)[0]
        line = cut + "..."
    return line or fallback
