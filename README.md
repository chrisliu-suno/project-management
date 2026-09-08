# spine

Carries project context across agent sessions, so the goal, the plan, and the standing rules
arrive on their own instead of being re-explained.

Requirements live in `~/dev/docs/project-spine/PRD.md` (private). This repo is the implementation
and is public — no work-specific content goes in it. Fixtures are synthetic.

## Using it

Three things a human does. Everything else runs from hooks.

**1. Register a project once.** Its documents live in their own directory, outside any repo, so
they survive branch switches and concurrent agents.

```sh
spine registry add --slug my-project --name "My Project" --docs-dir ~/dev/docs/my-project
```

**2. Open the dashboard and leave it open.** This is the only interface you need day to day. It
shows corpus health per project, what would be loaded for a given task, sessions running right
now with pause/stop/redirect controls, and any document edits waiting on a yes or no. The header
shows a count when something needs you.

```sh
spine serve      # http://127.0.0.1:8791
```

**3. Decide the proposals it queues.** When work ships that no document mentions, spine drafts the
edit and waits. Accept or reject in the dashboard; accepting appends to the document.

That is the whole manual surface. In particular you do not run the indexer, the fact observer, or
the proposal drafter — `spine refresh` does all three for every project, and it runs on a
schedule (see Scheduling).

### What happens without you

| When | What fires |
|---|---|
| a session starts | the project is identified from cwd and branch, and its every-time documents are injected |
| a session starts | the session declares itself, so it appears in the dashboard |
| an edit is attempted | the edit is checked against what the session said it was doing, and warns when it strays |
| a session stops | queued steering (pause, stop, redirect) is picked up and applied |

### Scheduling

`spine refresh` is the whole maintenance loop: observe what shipped, rebuild the graph, draft
proposals. Run it from a launchd agent so the dashboard is never stale:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.chrisliu.spine-refresh.plist
launchctl bootout gui/$(id -u)/com.chrisliu.spine-refresh   # to stop
```

To run it by hand, or to see what a sweep would report:

```sh
spine refresh                     # every project
spine refresh --project my-project
```

### Reviewing a draft before anyone reads it

```sh
spine critique check --file doc.md    # mechanical style notes, no model call
spine critique revise --file doc.md --write
```

## Modules

Each is independently replaceable. Depend on `ports.py`, never on a sibling's concrete class.

| Module | Package | Job |
|---|---|---|
| M1 | `spine.registry` | which projects exist; map a session to one or more |
| M2 | `spine.docs` | parse the corpus: frontmatter, kind, read-when group, size caps |
| M3 | `spine.index` | extract typed links from text; persist the graph |
| M4 | `spine.picker` | choose what a session gets, within a line budget; record every pick |
| — | `spine.session` | read and write the project stamp a session carries |
| — | `spine.classify` | assign kind and read-when with a model, cached by content hash |
| — | `spine.health` | corpus findings: orphans, caps, duplicate titles, missing brief |
| — | `spine.serve` | the dashboard: page, JSON reads, and the two POST routes |
| — | `spine.context` | attach a starting session to its projects and render its context |
| — | `spine.facts` | observe commits and merges; report where docs and reality diverge |
| — | `spine.live` | declared sessions, steering, broadcasts, leases |
| — | `spine.guard` | scope and steering checks at edit and publish boundaries |
| — | `spine.proposals` | draft document edits from facts; a human decides each one |
| — | `spine.critique` | style gate and the unattended critique-and-revise loop |
| — | `spine.refresh` | one sweep: observe, index, propose, for every project |

Shared contracts: `model.py` (types), `ports.py` (interfaces), `constants.py` (every limit and
well-known name), `paths.py` (state locations).

## State

Everything derived lives under `$SPINE_HOME` (defaults to `$XDG_STATE_HOME/spine`).

| File | Holds |
|---|---|
| `registry.toml` | project definitions |
| `graph.sqlite3` | docs and extracted links |
| `picks.sqlite3` | every context selection made |
| `sessions/` | per-session project stamps |
| `classifications.sqlite3` | model verdicts, keyed by content hash and prompt version |
| `facts.sqlite3` | observed commits and merged pull requests per project |
| `live_sessions.sqlite3` | declared sessions, steering queue, leases |
| `proposals.sqlite3` | proposed edits and how each was decided |

Documents themselves stay in each project's own directory, outside any repo, so they survive
branch switches and concurrent agents.

## Develop

```sh
uv sync
uv run pytest
uv run spine --help
```

## Conventions

- Constants only in `constants.py`; no literal limits or filenames elsewhere.
- Functions single-purpose, 40 lines max.
- Types over prose. Docstrings say what the code does and stop.
