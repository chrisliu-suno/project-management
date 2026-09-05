---
kind: decision_log
read_when: log
title: Decision log
---

# Decision log

Append only.

## Interval tree over periodic sweep
Status: decided.
Conflicts must be refused at insert time, which a sweep cannot do.
Cited by [design-scheduler.md](design-scheduler.md).

## Windows are half-open intervals
Status: decided.
Supersedes the closed-interval entry below. Closed intervals made a release at exactly the
boundary ambiguous.

## Windows are closed intervals
Status: superseded.
Superseded by the half-open decision above. Docs still carrying the closed-interval framing were
not swept in that pass.

## Station capability flags replace the name allowlist
Status: decided.
Became rule 3 in [project-rules.md](project-rules.md).
