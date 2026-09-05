---
kind: brief
read_when: every_time
title: Orbital Relay — brief
area: null
---

# Orbital Relay

Scheduling uplink windows for a fleet of ground stations. One station can talk to one satellite
at a time, and windows are short, so the scheduler has to be right rather than fast.

Where things stand: the uplink-window milestone is in flight. See
[milestone-uplink-window.md](milestone-uplink-window.md) for what it must do and
[design-scheduler.md](design-scheduler.md) for how the allocator works.

Standing rules that bind every task are in [project-rules.md](project-rules.md). Read those first.
Anything unresolved is in [open-questions.md](open-questions.md).
