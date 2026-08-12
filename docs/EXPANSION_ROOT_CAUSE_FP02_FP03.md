# Expansion: Why FP02 and FP03 Have Such Large Optimality Gaps

**Question:** `docs/EXPANSION_MILP_OPTIMALITY_GAPS.md` found that Neal and
Hybrid land ~91-110% above the certified optimum on FP02/FP03, versus 0-14%
on FP01/FP04/FP05. Why?

## Ruled out: a simple structural story

The paper's own framing (Sec. 8.2/9.3) attributes FP02/FP03's QPU embedding
failure to "dense logical interactions." It's natural to guess the same
density explains the classical/Hybrid solution-quality gap too. The
structural metrics don't support a clean version of that story:

| FP | rooms | exits | routes | branch factor | penalty A | retained interactions | density (retained / possible pairs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FP01 | 12 | 5 | 60 | 5.00 | 1.8897 | 954 | 53.90% |
| FP02 | 33 | 8 | 264 | 8.00 | 0.9193 | 13,675 | 39.39% |
| FP03 | 28 | 9 | 252 | 9.00 | 0.8369 | 12,421 | 39.27% |
| FP04 | 8 | 2 | 16 | 2.00 | 1.9631 | 77 | 64.17% |
| FP05 | 24 | 3 | 72 | 3.00 | 2.2129 | 1,751 | 68.51% |

FP02/FP03 have the *lowest* relative interaction density (39%) of all five --
lower than FP01 (54%), FP04 (64%), or FP05 (68%). If dense pairwise coupling
alone made the landscape hard for Neal/Hybrid, FP02/FP03 should be *less*
rugged by this measure, not more. Branching factor (choices per room: 8-9 for
FP02/FP03 vs. 2-5 for the rest) and penalty magnitude `A` (lowest for
FP02/FP03) both correlate directionally with the gap, but neither explains
FP01 vs. FP05 cleanly: FP01 has a *higher* branching factor than FP05 (5 vs.
3) and a *lower* penalty `A` (1.89 vs. 2.21), yet FP01's gap is far smaller
(1.08% vs. 6.60% for Hybrid). Structure alone isn't the whole story.

## What does track cleanly: raw problem size

| FP | variables | Hybrid gap (best run) |
|---|---:|---:|
| FP04 | 16 | 0.00% |
| FP01 | 60 | 1.08% |
| FP05 | 72 | 6.60% |
| FP03 | 252 | 91.27% |
| FP02 | 264 | 99.16% |

This is close to monotonic in variable count, and there's an obvious
mechanical candidate: **the paper uses a fixed annealing budget --
`NUM_READS=1000`, `NUM_SWEEPS=5000` -- for every floorplan**, from the
16-variable FP04 up to the 264-variable FP02
(`scripts/solve_qubo_neal.py`, lines 104-106). Simulated annealing's
required sweep count to reliably find good minima generically grows with
problem size; a fixed budget that's comfortably sufficient for 16-72
variables may simply be inadequate for 250+.

## Direct test: does more compute close the gap?

`scripts/expansion/neal_budget_scaling_test.py` reuses the *exact* same
penalized BQM construction as `solve_qubo_neal.py` (same
`build_base_coefficients`, same automatic-penalty formula, same pruning) --
the only variable is `num_sweeps`, run at 5,000 (the paper's baseline),
25,000, 100,000, and 500,000, each checked against the certified MILP
optimum.

| Floorplan | Sweeps | Reads | Best valid energy | Gap vs. MILP optimum |
|---|---:|---:|---:|---:|
| FP02 | 5,000 (baseline) | 200 | 0.679434 | 135.24% |
| FP02 | 25,000 (5x) | 200 | 0.688231 | 138.28% |
| FP02 | 100,000 (20x) | 200 | 0.662085 | 129.23% |
| FP02 | 500,000 (100x) | 200 | 0.665990 | 130.58% |
| FP03 | 5,000 (baseline) | 200 | 0.628632 | 141.77% |
| FP03 | 25,000 (5x) | 200 | 0.668837 | 157.23% |
| FP03 | 100,000 (20x) | 200 | 0.538303 | 107.03% |
| FP03 | 500,000 (100x) | 200 | 0.584804 | 124.91% |

**The gap does not close with more compute.** A 100x increase in sweeps
(5,000 -> 500,000) leaves both floorplans oscillating in roughly the same
range (FP02: 129-138%, FP03: 107-157%), with no monotonic trend toward the
certified optimum. This directly rules out "the paper just didn't run Neal
long enough" as the primary explanation -- more annealing time doesn't help
here, which means the search is not merely under-sampled, it is getting
**trapped**: something about these two landscapes creates deep, wide local
minima that dominate regardless of anneal length.

That reframes the question from "how much compute is needed" to "what makes
the landscape trap the search in the first place" -- which is a structural/
geometric question, answered in
`docs/EXPANSION_GEOMETRY_BOTTLENECK_COMPARISON.md`.

## Interpretation

Combining this with the geometric analysis: FP02 and FP03 have roughly
**2-25x more structural bottlenecks** than FP01/FP04/FP05 by every measure
computed there -- bridge edges, critical bridges (bridges shared by >=2
rooms), capacity-bottleneck edges, mean route length, and (for FP03
specifically) corridor diameter. Each bridge/bottleneck edge is a hard
coupling point in the QUBO's congestion term: multiple rooms' route choices
interact strongly through it, and satisfying one room's preference to avoid
overloading it can conflict with another's. More such coupling points means
more opportunities for the penalty landscape to have many similar-depth
local minima that are locally stable (no single-variable flip improves
things) but far from global optimum -- exactly the failure mode simulated
annealing is known to struggle with, and exactly what "more sweeps didn't
help" would look like if this is the mechanism.

**Working hypothesis** (needs a larger floorplan corpus to confirm
statistically -- see Tier 2): optimality gap for this formulation is driven
less by raw variable count and more by the density of *structural*
bottlenecks (bridges/critical bridges) relative to problem size, which is
itself a product of building geometry (long single corridors, few redundant
paths) rather than room/exit count alone. FP03 (dormitory: long central
corridor, few loops) is the most bottleneck-dense floorplan in the set and
also has the largest optimality gap; FP04 (museum: short, highly symmetric,
3 bridges total) has the fewest bottlenecks and a 0% gap.
