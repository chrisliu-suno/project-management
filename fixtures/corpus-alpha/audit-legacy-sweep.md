---
kind: area_design
read_when: rarely
title: Audit — the legacy sweep
area: uplink
---

# Audit — the legacy sweep

Findings from reading the sweep implementation before replacing it. Nothing links here, which is
the point: this document exists and is findable only by walking the directory.

The sweep ran every 30 seconds and compared each station's reservations pairwise. It missed
conflicts created and resolved inside one interval, and it treated a window ending at exactly the
same instant another began as overlapping.
