# Expansion: Statistical Confirmation Across 23 Floorplans

**Question:** `EXPANSION_GEOMETRY_BOTTLENECK_COMPARISON.md` proposed that
structural bottleneck density (bridges, critical bridges) -- not raw
variable count -- explains why FP02/FP03 have such large optimality gaps.
That was based on n=5. This tests it properly, with a controlled synthetic
corpus.

## Method

Real floorplans differ in many confounded ways at once (size, topology,
room/exit ratio), so 5 data points can't separate "bigger" from
"structurally worse." `scripts/expansion/generate_synthetic_floorplan.py`
generates floorplans in the exact same CSV schema as FP01-FP05, with three
**controlled corridor topologies**, each at 3 sizes (10/20/30 rooms) and 2
random seeds (occupancy/capacity only -- topology is deterministic given
size), giving 18 additional floorplans:

- **linear**: single corridor spine, rooms along its length. Maximum
  structural bottleneck by design -- nearly every corridor edge is a bridge.
- **tree**: branching spine, rooms on short branches. Many bridges (a tree
  has zero cycles -- literally every edge is a bridge) but each is shared by
  only the few rooms on its branch.
- **loop**: corridor forms one ring, rooms attached around it. Minimal
  structural bottleneck -- the ring gives every hallway edge an alternate
  path, so almost none are bridges.

All 18 passed the repository's own test suite unmodified (`pytest` --
`available_floorplans()` auto-discovers new floorplan folders, so this is
the same connectivity/door-degree/reachability validation FP01-FP05 get, not
a separate check). Each was solved to certified optimality with the MILP
script, then solved once with Neal at the paper's exact baseline settings
(1,000 reads, 5,000 sweeps, seeds 42-45) for a gap measurement directly
comparable across all 23 floorplans (the 5 real floorplans were also re-run
with this identical single-run setting, rather than reusing their 30-run
benchmark best, to avoid mixing aggregation methods).

**Known limitation, stated up front:** synthetic rooms connect directly to
their door (no interior room-tile grid, unlike the real floorplans) -- see
the generator's docstring. This shouldn't affect the corridor-network
structural metrics the hypothesis is about, but the synthetic corpus's
absolute route-hop counts aren't directly comparable to the real floorplans'
in magnitude, only in relative ordering.

## Result 1: structure matters, not just size (confirmed)

n=23. Every structural candidate correlates significantly with Neal's
optimality gap:

| Predictor | Pearson r | p-value | Spearman rho |
|---|---:|---:|---:|
| n_variables | 0.834 | <0.0001 | 0.851 |
| **corridor_diameter_hops** | **0.865** | **<0.0001** | **0.890** |
| route_hops_mean | 0.721 | 0.0001 | 0.730 |
| structural_critical_bridge_count | 0.723 | 0.0001 | 0.659 |
| structural_bridge_count | 0.626 | 0.0014 | 0.755 |
| capacity_bottleneck_edge_count_over_1x | 0.652 | 0.0008 | 0.748 |
| traffic_bottleneck_top1_share_of_rooms | 0.686 | 0.0003 | 0.754 |

Corridor diameter -- the longest shortest-path *within the hallway network
alone*, independent of any room -- is a **stronger** predictor than raw
problem size. That alone rules out "it's just a bigger problem" as the full
story.

## Result 2: the original bridge-count framing was too narrow (a real correction, not just confirmation)

The controlled synthetic corpus produces a size-matched ordering that a
pure bridge-count story gets wrong:

| Topology | Rooms | Critical bridges | Corridor diameter | Neal gap |
|---|---:|---:|---:|---:|
| loop | 20 | **4** | 8 | 20-24% |
| tree | 20 | **17** | 7 | 7-11% |
| loop | 30 | **6** | 12 | 64-71% |
| tree | 30 | **30** | 11 | 19-28% |

Tree has **4-5x more critical bridges** than loop at matched room counts,
yet a **smaller** gap both times. Critical-bridge count does not order these
three topologies correctly (it predicts loop < tree < linear; the actual
gap ordering is tree < loop < linear). Corridor diameter and mean route
length *do* order all three topologies correctly at every size tested.

This makes physical sense on reflection: a tree's bridges are each shared by
only the handful of rooms on that specific short branch, while a loop routes
*every* room's traffic through the same single ring -- concentrating
congestion onto shared capacity is what hurts, not the literal count of
non-redundant edges. Route/corridor length is a better proxy for how much
combinatorial interaction accumulates per room's decision than bridge count
is.

## Result 3: corridor diameter adds real explanatory power beyond size (confirmed, quantified)

Partial correlation of corridor diameter with the gap, controlling for
`n_variables`: **r = 0.756, p < 0.0001**.

| Model | R² |
|---|---:|
| `gap ~ n_variables` alone | 0.696 |
| `gap ~ n_variables + structural_critical_bridge_count` | 0.729 (+0.033) |
| `gap ~ n_variables + corridor_diameter_hops` | **0.870 (+0.174)** |

Corridor diameter explains roughly **5x more additional variance** than
critical-bridge count does, after controlling for problem size. This is the
headline structural predictor, not bridge/bottleneck counts.

## Revised working conclusion

The original hypothesis (structure matters, not just size) is confirmed and
now has real statistical support across 23 floorplans, not 5. The specific
mechanism is refined: **corridor/route length -- how far traffic has to
travel through shared infrastructure -- predicts the optimality gap better
than how many non-redundant (bridge) edges exist.** FP03's dormitory-style
40-hop corridor spine (`EXPANSION_GEOMETRY_BOTTLENECK_COMPARISON.md`) is
consistent with this: it's not just that FP03 has many bridges, it's that
its single corridor is unusually long.

## What's still open

- n=23 with 18 controlled + 5 real is enough to establish the direction and
  approximate effect size, not to fully separate corridor diameter from
  route-hop-mean (r=0.721, likely correlated with diameter) -- a larger
  synthetic sweep varying diameter independently of hop-count would sharpen
  this further.
- This was tested against Neal only (single run, paper-baseline settings).
  Confirming the same ordering holds for Hybrid, and running enough repeats
  per synthetic floorplan for its own significance test (as in Tier 1 for
  the original 5), is the natural next step.
- The synthetic generator's room-to-door simplification (no interior
  navigation grid) should be revisited if this result is used beyond
  directional confirmation -- e.g. if a future paper wants to report
  synthetic-corpus numbers on the same footing as the real floorplans, not
  just the same ordering.

All raw data: `docs/expansion_statistical_confirmation_raw.json`,
`docs/expansion_synthetic_geometry_raw.json`,
`docs/expansion_synthetic_neal_results.json`.
