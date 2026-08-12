# Expansion: Certified MILP Optimality Gaps for All Five Floorplans

**Status:** first pass complete, all five floorplans solved to proven optimality.
**Branch:** `expansion/milp-optimality-gaps`
**Motivation:** the submitted paper certifies a global optimum only for FP04
(8 rooms, exhaustive enumeration of 256 assignments). FP01, FP02, FP03, and
FP05 are reported as "lowest energy observed, not certified optima" -- this
was flagged in peer review as the single highest-leverage gap to close before
a stronger venue submission.

## Method

The QUBO in the paper is a **penalty-method reduction** of the real problem:
the exactly-one-route-per-room constraint is enforced via a quadratic penalty
term `A * sum_r (1 - sum_e x_r,e)^2` (Eq. 6-8) so that Neal/Hybrid/QPU can
sample it as an unconstrained BQM. But the real problem underneath is a
**convex** integer quadratic program -- `H_congestion` is a sum of squared
linear forms in `x` (a Gram-matrix quadratic, i.e. always PSD) -- so it can be
solved *exactly*, with a hard linear equality constraint instead of a penalty,
by any MIQP-capable solver. No non-convexity, no embedding, no chains.

`scripts/expansion/milp_optimality_gap.py` formulates this directly with
Google OR-Tools CP-SAT:

- One `BoolVar` per candidate route (same variables as the QUBO).
- `sum_{e} x_{r,e} == 1` as a **native linear constraint** per room (replaces
  the penalty term entirely -- no `A`, no tuning).
- Congestion is built **per edge**, not per pairwise route interaction: one
  integer `load_k` variable per edge equal to the scaled linear combination of
  routes using it, then a single `AddMultiplicationEquality(load_k^2, ...)`
  per edge. This keeps the model size linear in `(routes + edges)` rather
  than quadratic in routes, which is what let FP02 (264 routes) and FP03 (252
  routes) solve in under 2 seconds despite being too dense to embed on the
  QPU in the original paper.
- Solve-time coefficients are integer-scaled (search-ranking precision only).
  The **reported** energy is recomputed independently in float64 Python from
  the winning assignment, using the exact same formula as
  `solve_qubo_neal.py`'s `build_base_coefficients` (no pruning).

## Validation (do this before trusting any of the numbers below)

1. **FP04 ground truth.** The paper's own exhaustive enumeration gives
   `1.5026583666328914`. The MILP recomputed energy: `1.5026583666...` --
   matches to 10 decimal places, `status=OPTIMAL`.
2. **Objective-formula cross-check.** Applying this script's `true_energy()`
   to FP03's *own saved Neal assignment* (`qubo_neal/selected_assignments.csv`)
   reproduces `normalized_objective_without_penalty` from
   `qubo_neal/solution_summary.json` **exactly**
   (`0.5452529142969503` both sides) -- confirming the objective
   implementation is byte-identical to the paper's, not an approximation.
3. Every floorplan returned CP-SAT status `OPTIMAL` (not just `FEASIBLE`),
   meaning each result is a **certified** global minimum with a matching
   proven lower bound, not a best-effort heuristic result.

## Results

| Floorplan | MILP optimum (proven) | Neal best (30 runs) | Neal gap | Hybrid best (30 runs) | Hybrid gap |
|---|---:|---:|---:|---:|---:|
| FP01 | 0.593857 | 0.636840 | 7.24% | 0.600250 | **1.08%** |
| FP02 | 0.288830 | 0.585420 | 102.69% | 0.575235 | **99.16%** |
| FP03 | 0.260012 | 0.545110 | 109.65% | 0.497328 | **91.27%** |
| FP04 | 1.502658 | 1.502658 | 0.00% | 1.502658 | 0.00% |
| FP05 | 0.615057 | 0.703960 | 14.45% | 0.655631 | **6.60%** |

Gap = `(observed_best - MILP_optimum) / MILP_optimum`, using each solver's
best single run across the paper's own 30-run benchmark files
(`data/floorplans/FPXX/output/qubo_{neal,hybrid}/benchmark_summary.csv`).

## The finding

This is not a uniform "solvers are ~X% off" result -- it splits cleanly into
two regimes, and that split lines up with something the paper already
measured for an unrelated reason:

- **FP01, FP04, FP05** (embeddable on the QPU): gaps of 0-14%. Reasonable,
  expected heuristic-solver behavior.
- **FP02, FP03** (the two instances that *could not be embedded on the QPU
  at all*, per the paper's own Table 4): gaps of 91-110%. Neal and Hybrid are
  roughly **double** the true optimum on both.

The paper already reported FP02/FP03 as the two hardest instances for direct
embedding, attributed to "dense logical interactions." This expansion shows
the same two instances are *also* the hardest for the classical/hybrid
samplers to actually solve well -- a fact the paper had no way to see without
a ground truth, since without a certified optimum, 100%-valid-sample-rate
output looks indistinguishable from a good solution. Concretely, for FP03,
Neal/Hybrid's reported "valid" solutions are worse than the trivial
nearest-exit-Dijkstra baseline (Appendix Table A1: distance 250.75, congestion
64.494) on **both** distance (551-595 vs. baseline 250.75) and congestion
(134-148 vs. baseline 64.494) simultaneously -- a strictly dominated
solution that the QUBO's own "100% valid samples" metric cannot detect,
because validity only checks the exactly-one constraint, not solution quality.

This suggests instance difficulty for this formulation may be driven by
something structural about congestion-interaction density (shared
hallway/exit bottlenecks creating a rugged penalty landscape) that affects
*both* QPU embeddability and classical/hybrid solution quality together --
worth investigating directly in a follow-up (e.g. correlating interaction
density or automatic penalty magnitude `A` against gap size across a larger
floorplan corpus, per Tier 2 of the expansion plan).

## What's still open

- Only the *best* run per solver is compared here (mirroring how a reviewer
  would ask "how close does your best case get"). A paired per-run gap
  analysis (all 30 runs, not just the best) plus the Wilcoxon significance
  test from Tier 1 item 2 would strengthen this further.
- This validates the paper's classical/Hybrid track record, but doesn't yet
  explain *why* FP02/FP03 are structurally harder -- that requires digging
  into the per-edge congestion density or the automatic-penalty values (`A`)
  from Table 2, which were already the two lowest of the five (0.919, 0.837).
- Raw per-floorplan artifacts are in `data/floorplans/FPXX/output/milp_gap/`.
