# bench

Offline replicas of solved challenges, run across nine models.

- `P1/`, `P2/` — self-sufficient replica briefs (one per challenge), each with
  a local mock endpoint reproducing the live API's shape and limits
- `scoring/` — deterministic graders; every metric is a number a script computed
- `results/` — per-run reports from the fleet, and the aggregated 3×3 grid

Rules: the live course API is never called from the bench. Ground truth comes
from the integrator's live run. Every model gets an identical brief, an
identical mock, and an identical grader.
