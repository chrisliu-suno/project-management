---
kind: rollout
read_when: in_area
title: Rollout and ramp — uplink windows
area: uplink
---

# Rollout and ramp — uplink windows

## Gate order

1. `allocator-interval-tree` at 0% — shadow only, compare against the legacy sweep.
2. Widen to 5% after mismatches sit under 0.1% for 48 hours.
3. Widen to 50% after a full solstice boundary passes clean.
4. Enforce.

## Watch

| Signal | Threshold | If breached |
|---|---|---|
| shadow mismatch rate | above 0.1% | hold, do not widen |
| allocation latency p99 | above 400ms | hold |
| refused-but-should-grant | any | back out immediately |

## Hard blockers

- `allocator-interval-tree` must have soaked 48 hours before enforce widens past 5%.

Ramps [milestone-uplink-window.md](milestone-uplink-window.md).
