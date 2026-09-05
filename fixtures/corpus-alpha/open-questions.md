---
kind: open_questions
read_when: log
title: Open questions
---

# Open questions

- **open** — what happens to an in-flight burst when a station drops mid-window. Owner:
  scheduler. Settled by: deciding whether partial bursts are resumable at all.
  Blocks [milestone-uplink-window.md](milestone-uplink-window.md).
- **assumption** — the interval tree stays small enough to hold per station in memory. If a
  station ever serves more than a few thousand future windows this breaks.
- **open** — whether the solstice clock boundary needs its own test harness. Owner: unassigned.
