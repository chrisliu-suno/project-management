---
kind: milestone
read_when: in_area
title: Milestone — uplink window allocation
area: uplink
---

# Milestone — uplink window allocation

## What must be true when this is done

- A satellite is never allocated two overlapping windows on the same station.
- A window released early is available to the next requester within one scheduling tick.
- A station going offline releases its future windows without operator action.

## Scenarios that prove it

**Double-booking is refused.** Given station S has a window for satellite A from 10:00 to 10:04,
when satellite B requests 10:02 to 10:06 on S, then the request is refused and A keeps its window.

**Early release is reusable.** Given A holds 10:00 to 10:04 and releases at 10:01, when B requests
10:01 to 10:03 on S, then B is granted it.

**Offline station drains.** Given S holds three future windows, when S reports offline, then all
three are released and their owners are notified.

Implements the fleet-throughput goal in [brief.md](brief.md). Released by
[rollout-uplink.md](rollout-uplink.md). Coverage in
[test-coverage-uplink.md](test-coverage-uplink.md).
