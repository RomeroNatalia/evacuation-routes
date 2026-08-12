# Expansion: Geometric Comparison of the Five Floorplans

Computed by `scripts/expansion/geometry_bottleneck_analysis.py` from the raw
`graph_nodes.csv` / `graph_edges.csv` inputs (not the QUBO outputs), plus the
route catalog for chain-length and traffic metrics. Full per-floorplan
numbers, including the top-5 edges for each bottleneck measure, are in
`docs/expansion_geometry_bottleneck_raw.json`.

## Points, rooms, exits, hallways

| FP | total nodes | rooms | exits | doors | hallway nav. nodes | in-room nav. nodes |
|---|---:|---:|---:|---:|---:|---:|
| FP01 | 173 | 12 | 5 | 13 | 34 | 109 |
| FP02 | 584 | 33 | 8 | 55 | 107 | 381 |
| FP03 | 571 | 28 | 9 | 45 | **204** | 285 |
| FP04 | 173 | 8 | 2 | 12 | 8 | 143 |
| FP05 | 359 | 24 | 3 | 30 | 66 | 236 |

"Hallway nodes" excludes in-room floor tiles (`space_type=room`) and counts
only true corridor nodes (`space_type=hallway`) among the `navigation`-typed
points. FP03 has roughly **double** the corridor nodes of FP02 despite fewer
rooms (28 vs. 33) -- consistent with a dormitory's long central-corridor
layout versus an office/school's more branching one.

## Chain lengths

| FP | route hops (mean/max) | route distance (mean) | corridor diameter (hops) | corridor connected components |
|---|---|---:|---:|---:|
| FP01 | 15.4 / 25 | 8.6 | 21 | 1 |
| FP02 | 28.6 / 48 | 22.7 | 22 | 1 |
| FP03 | 27.5 / 49 | 21.5 | **40** | 1 |
| FP04 | 12.6 / 19 | 8.6 | 5 | 1 |
| FP05 | 19.2 / 32 | 10.7 | 22 | 1 |

Two different "chain length" measures, both worth having: **route hops** is
how long an individual room's evacuation path is (room to exit); **corridor
diameter** is the longest shortest-path *within the hallway network itself*
(hallway to hallway), independent of any specific room. FP03's corridor
diameter (40) is nearly double every other floorplan -- a single long spine
corridor, exactly the dormitory-hallway intuition.

## Symmetry

| FP | vertical mirror | horizontal mirror | 180° rotation | best |
|---|---:|---:|---:|---:|
| FP01 | 0.80 | 0.61 | 0.58 | 0.80 |
| FP02 | 0.66 | 0.51 | 0.49 | 0.66 |
| FP03 | 0.75 | 0.58 | 0.55 | 0.75 |
| FP04 | 1.00 | 0.94 | 0.94 | **1.00** |
| FP05 | 0.77 | 0.60 | 0.57 | 0.77 |

Fraction of nodes with a same-type node at the mirrored position, best of
three candidate symmetries (vertical-axis mirror, horizontal-axis mirror,
180° point rotation), each through the node-set centroid. FP04 (the museum,
0% optimality gap) is perfectly symmetric; FP02 (99% gap) is the least
symmetric layout in the set. Symmetry and optimality gap track loosely here,
but geometry alone (next section) explains it more directly.

## Bottlenecks -- three definitions, because one number isn't enough

No single metric captures "bottleneck-ness." These three are independently
motivated and measure different things:

**1. Capacity bottleneck** (reuses the paper's own math): for edge *k*,
`max_feasible_load[k]` = the worst-case simultaneous utilization if every
room picked whichever of its candidate routes taxes *k* hardest. This is
exactly the quantity `compute_objective_scales()` already computes to build
the congestion normalizer -- here it's reported per-edge instead of only
summed into one scale constant.

**2. Traffic-concentration bottleneck** (pure topology, no capacity): for
edge *k*, `route_multiplicity[k]` = how many distinct candidate routes use
it at all. High multiplicity means many rooms' plans structurally converge
there, regardless of how much capacity it has.

**3. Structural bottleneck** (pure connectivity): bridge edges (removal
disconnects the graph) and, specifically, *critical bridges* -- bridges that
lie on the recorded path of two or more different rooms. A critical bridge
is a literal single point of failure no candidate route can avoid for more
than one room at once.

| FP | capacity-BN edges (>1.0x) | max traffic multiplicity | bridges | critical bridges | max rooms sharing one bridge |
|---|---:|---:|---:|---:|---:|
| FP01 | 61 | 150.0% of rooms | 34 | 13 | -- |
| FP02 | **183** | 281.8% of rooms | **70** | **33** | -- |
| FP03 | 171 | 246.4% of rooms | **81** | **41** | -- |
| FP04 | 70 | 100.0% of rooms | 3 | 2 | -- |
| FP05 | 36 | 154.2% of rooms | 54 | 22 | -- |

(`max rooms sharing one bridge` is in the raw JSON per floorplan; omitted
here for space -- pull `structural_max_rooms_sharing_one_bridge` if needed.)

FP02 and FP03 have **2-25x more bridges and critical bridges** than FP01/
FP04/FP05, and the most capacity-bottleneck edges by a wide margin. FP04 is
the outlier worth noting: it has a *high* capacity-bottleneck-edge count (70)
despite being tiny and having a 0% optimality gap -- capacity bottlenecks
alone don't explain difficulty. Structural bottlenecks (bridges/critical
bridges) track the optimality gap far more cleanly than any single other
measure here.

## Bottom line

FP02 and FP03 are not just "the two biggest floorplans" -- they are the two
*structurally most fragile* ones: the most bridges, the most bridges shared
across multiple rooms, the longest routes, and (FP03 specifically) by far
the longest single corridor. That structural fragility is the most direct
available explanation for why they're also the two floorplans where more
compute (see `EXPANSION_ROOT_CAUSE_FP02_FP03.md`) does not close the
optimality gap -- the landscape has many locally-stable-but-globally-poor
configurations to get stuck in, and no amount of extra annealing time
escapes a trap of that kind.
