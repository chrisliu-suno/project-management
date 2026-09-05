---
kind: area_design
read_when: in_area
title: Area design — the allocator
area: uplink
---

# Area design — the allocator

The allocator keeps an interval tree per station. A request is a closed interval; granting it
inserts, releasing removes. Conflicts are detected on insert rather than on a periodic sweep.

Interval bounds follow [the closed-interval decision](decisions.md#windows-are-closed-intervals).

## What lost

**Periodic conflict sweep.** Simpler, but a conflict is only visible after it exists, and rule 1
in [project-rules.md](project-rules.md) makes that unacceptable.

**Per-satellite locks.** Would serialize the whole fleet behind one slow station.

Surfaces here are classified by [classification.md](classification.md).
