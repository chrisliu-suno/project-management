# spine

Carries project context across agent sessions, so the goal, the plan, and the standing rules
arrive on their own instead of being re-explained.

Requirements live in `~/dev/docs/project-spine/PRD.md` (private). This repo is the implementation
and is public — no work-specific content goes in it. Fixtures are synthetic.

## Modules

Each is independently replaceable. Depend on `ports.py`, never on a sibling's concrete class.

| Module | Package | Job |
|---|---|---|
| M1 | `spine.registry` | which projects exist; map a session to one or more |
| M2 | `spine.docs` | parse the corpus: frontmatter, kind, read-when group, size caps |
| M3 | `spine.index` | extract typed links from text; persist the graph |
| M4 | `spine.picker` | choose what a session gets, within a line budget; record every pick |
| — | `spine.session` | read and write the project stamp a session carries |

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
