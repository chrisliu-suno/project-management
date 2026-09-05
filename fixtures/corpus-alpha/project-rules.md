---
kind: project_rules
read_when: every_time
title: Project rules
---

# Project rules

Standing rules. These bind every task, whatever it is. Accrued as we hit them.

1. **Never widen a window without releasing the conflicting reservation first.** Overlapping
   reservations are unrecoverable once a burst starts.
2. **A test must pin the clock it assumes.** Unpinned tests pass locally and fail at the
   solstice boundary.
3. **No station is special-cased by name.** Capability flags only.

Rule 1 constrains [design-scheduler.md](design-scheduler.md) and every task under
[milestone-uplink-window.md](milestone-uplink-window.md).
