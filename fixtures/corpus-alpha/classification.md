---
kind: classification
read_when: every_time
title: Classification lookups
---

# Classification lookups

Look these up. Do not re-derive them.

| If the request looks like this | It is | So |
|---|---|---|
| caller already holds a signed window token | possession | validate the token, do not re-check the schedule |
| caller is asking what windows exist | listing | full schedule check, filtered to their fleet |
| caller names a station directly | possession | token required |
| caller passes a fleet id only | listing | schedule check |

This classifies the surfaces described in [design-scheduler.md](design-scheduler.md).
