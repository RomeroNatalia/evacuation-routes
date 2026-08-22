# Optimality Gaps and Structural Bottleneck Analysis for Capacity-Aware Indoor Evacuation Route Assignment Using QUBO Optimization and Quantum Annealing

*(Draft v4)*

**Authors:** Arielle Jenna Fishman¹, Natalia Romero, Ph.D.¹
¹ Florida Atlantic University, Machine Perception and Cognitive Robotics Laboratory

> This is a plain-Markdown rendering of `main_v4.tex`, generated so the latest draft is readable directly on GitHub without a LaTeX compiler. The `.tex` file is the source of truth — if the two ever disagree, trust the `.tex`.

---

## Revision Notes (v3 → v4)

v3 (`paper/main.tex`) disclosed, but did not fix, two open issues in the synthetic-corpus analysis (Section 9.6): (i) whether the pruned-vs-unpruned energy bug already found and fixed for the 5-benchmark-floorplan comparison (Table 4) also affected the 10-repeat synthetic-corpus dataset, and (ii) that the Loop and Tree topologies' generator produced some short diagonal connector edges rather than pure axis-aligned corridors.

v4 resolves both, independently and for free initially (no D-Wave Leap quota spent on the diagnostic), then completed the Hybrid side too:

**Pruned-vs-unpruned (confirmed negligible).** Recomputing the true unpruned energy from each winning Neal assignment across all 18 (regenerated) synthetic floorplans, the difference from the pruned-BQM search energy is at most 0.68 percentage points — consistent with the spot-check already in v3's Limitations (max 0.26% on 3 floorplans) and the original 5-floorplan figure (<0.4%). This bug does not change any reported conclusion.

**Diagonal edges (a real effect, now fixed).** A diagonal edge in the generator moves both in x and y in a single hop, while every edge is hardcoded to `distance=1.0` regardless of angle — so a diagonal edge was a genuine one-hop shortcut a real, wall-respecting corridor could not take (going around the corner would take two axis-aligned hops). This affected Loop's door-to-corridor edge (one per room) and ring-to-exit edge (one per exit), and Tree's spine-to-first-branch-node edge (one per branch); Linear was unaffected. Fixed by routing each through an axis-aligned elbow node instead, and regenerated all 18 synthetic floorplans under new `_V2` IDs (see "Correcting a geometry artifact" below), leaving the original 18 untouched for direct comparison.

**What this changes.** Loop's and Tree's measured optimality gaps drop substantially once the shortcut is removed (Loop: up to −21 percentage points at 30 rooms; Tree: up to −6.65pp), while Linear — which never had diagonal edges — is essentially unchanged, confirming the effect is real and not solver noise. The paper's central qualitative finding survives, and if anything strengthens: corridor diameter remains exactly tied between Tree and Loop at matched room counts after the fix, and in the correlation analysis, corridor diameter is now the single strongest predictor (r=0.868, overtaking variable count's 0.826, itself down from v3's 0.865), while bridge-count measures got weaker (0.622 → 0.457).

**Hybrid re-run: complete.** 180 Hybrid calls (10 repeats × 18 V2 floorplans) were run on the diagonal-fixed corpus. Hybrid's mean gap is lower than Neal's in 17 of 23 instances and Bonferroni-significant (Mann-Whitney U, α=0.05/23) in 11 of 23, both lower and significant in 10 of 23 — essentially unchanged from v3's 18/23, 16/23, 11/23, confirming the Hybrid-outperforms-Neal finding was not an artifact of the diagonal-edge bug. The correlation and gap tables below include both solvers. The paper's main tables (Tables 7, 9, and the appendix) still show the v3/original-corpus numbers as originally published; the "Correcting a geometry artifact" section is where the V2-corrected numbers live for this draft.

---

## Abstract

This paper formulates static indoor evacuation-route assignment as a capacity-aware Quadratic Unconstrained Binary Optimization (QUBO) problem, solves it with classical simulated annealing, D-Wave Leap Hybrid, and direct quantum annealing across five manually constructed benchmark building layouts (16 to 264 logical variables), and then goes further than prior work of this kind in three ways.

First, we formulate the same constrained objective in Google OR-Tools CP-SAT using a scaled-integer representation. CP-SAT reaches status `OPTIMAL` for every floorplan tested in under two seconds, and the returned assignments are rescored independently under the original unpruned float64 objective. This reference baseline reveals that Neal and D-Wave Hybrid, previously reported as producing good solutions, are approximately 94–125% above the reference energy on two of the five floorplans, a gap invisible without an exact solver-side optimum for the scaled formulation.

Second, we investigate why: a controlled compute-budget experiment (up to 100× the original sweep count) fails to close the gap, ruling out under-sampling as the sole explanation, while a structural/geometric analysis and an 18-floorplan synthetic corpus with independently controlled corridor topology (linear, branching, and looped) identify *corridor diameter* — not bridge/bottleneck-edge count, our initial hypothesis — as a predictor comparably strong to raw problem size (r≈0.83) that nonetheless captures independent information, adding up to 13 additional percentage points of explained variance beyond variable count alone in a joint regression. This finding replicates under both classical and hybrid quantum solvers with proper significance testing (Mann-Whitney U, Bonferroni-corrected across 23 floorplans).

Third, we report formal significance tests throughout, correcting the descriptive-statistics-only limitation of the original study. The result is a fully reproducible evacuation-QUBO workflow with a substantially stronger classical reference baseline than prior work in this line, and an empirically grounded, statistically confirmed account of what makes a floorplan hard for current annealing-based solvers.

**[v4]** A geometry bug in the synthetic-corpus generator — diagonal connector edges acting as uncredited one-hop shortcuts in the Loop and Tree topologies — is identified, fixed, and the corpus regenerated; both Neal (free) and Hybrid (180 calls) were re-run on the corrected corpus. Measured optimality gaps drop substantially for the affected topologies under both solvers (Loop: up to −21pp Neal, −19pp Hybrid), while the paper's central structural finding survives and strengthens under both: corridor diameter becomes the single strongest predictor of solver difficulty for Neal (r=0.868) and Hybrid (r=0.853), ahead of raw variable count for both. The Hybrid-outperforms-Neal finding itself is essentially unchanged (11 of 23 both lower and Bonferroni-significant, vs. 11 of 23 originally).

**Keywords** — evacuation routing, QUBO, quantum annealing, capacity-aware optimization, minor embedding, integer optimization, D-Wave, simulated annealing

---

## 1. Introduction

Emergency evacuation planning requires people to move from occupied spaces to safe exits along legal and understandable routes. Practical evacuation guidance emphasizes clearly identified exits, unobstructed routes, and floorplans that show how occupants can leave a building without entering hazardous or inaccessible areas (OSHA). From an optimization perspective, however, assigning every room to its individually nearest exit can concentrate many occupants on the same doorway or corridor. A short route for each individual group is therefore not necessarily the best coordinated assignment for the building as a whole.

Building evacuation has long been represented as a network problem with nodes, arcs, capacities, and bottlenecks (Chalmet et al.). Classical facility-to-exit assignment work also shows that coordinated assignments can outperform simple nearest-exit rules (Kang et al.). Modern indoor guidance methods incorporate corridor capacity, congestion, risk, and changing conditions (Desmet & Gelenbe; Zhang et al.; Ye et al.). These approaches motivate a system-level objective that balances route efficiency against shared infrastructure rather than minimizing geometric distance alone.

The Machine Perception and Cognitive Robotics Laboratory fellowship notebooks develop a progression from identifying binary decisions, objectives, and constraints to building Binary Quadratic Models (BQMs), sampling them with classical simulated annealing, and executing them on D-Wave Hybrid and direct quantum hardware. The original capstone project applied that progression to a larger original problem: representing five manually constructed benchmark building layouts as validated wall-aware graphs, precomputing one legal route for each room-exit pair, and formulating the global assignment as a QUBO whose pairwise interactions penalize occupancy concentration on shared low-capacity edges.

That original study asked how effectively classical simulated annealing, a cloud Hybrid solver, and direct quantum annealing solve this QUBO as floorplan size and logical connectivity increase, and reported energy, physical route metrics, feasibility, runtime, and direct-QPU embedding behavior across 390 repeated solver runs. It found Hybrid consistently outperforming Neal, exact global optimality confirmed by exhaustive enumeration for the smallest 8-room floorplan, and two floorplans (FP02, FP03) whose density prevented direct embedding on the QPU altogether — but it explicitly acknowledged, as a limitation, that results for the four larger floorplans were *lowest observed energies, not certified optima*, and that no exact integer-optimization baseline or formal significance test was included.

This paper closes much of that gap, and in doing so substantially revises the picture the original results supported. We formulate the same constrained distance-plus-congestion objective in OR-Tools CP-SAT using scaled integer coefficients and solve that formulation to CP-SAT status `OPTIMAL` in under two seconds for every floorplan tested, including the two that could not be embedded on the QPU at all. The returned assignments are then rescored under the original unpruned float64 objective. Measured against these reference energies rather than only against each other, Neal and Hybrid are far from the reference solution on exactly the two floorplans the original study already flagged as structurally unusual — approximately 94–125% above it, rather than the small margins their mutual comparison suggested. We then investigate why, first ruling out insufficient compute budget directly (a 100× sweep-count increase does not close the gap), then building a geometric/topological analysis of the floorplans' navigation graphs, and finally constructing an 18-floorplan synthetic corpus with independently controlled corridor topology to test candidate structural explanations under conditions the five benchmark floorplans cannot provide. The result corrects our own initial hypothesis (bridge/bottleneck-edge count) in favor of a cleaner, better-supported one (corridor diameter), replicated with proper significance testing under both solvers evaluated.

**The contributions are:**
- A reproducible wall-aware floorplan-to-graph workflow for five manually constructed benchmark building layouts (retained from the original study).
- A room-group QUBO combining normalized route distance with occupancy-weighted, capacity-normalized shared-edge congestion (retained from the original study).
- A controlled comparison of Neal simulated annealing, D-Wave Leap Hybrid, and direct-QPU execution using repeated independent runs (retained from the original study).
- **New:** a CP-SAT scaled-integer reformulation solved to status `OPTIMAL` for all five floorplans — not only the smallest — and all 18 synthetic instances, with each returned assignment rescored under the original unpruned objective, exposing optimality gaps of 94–125% on two floorplans that a solver-vs-solver comparison alone cannot reveal.
- **New:** formal significance testing (Mann-Whitney U, Bonferroni-corrected) replacing the descriptive-statistics-only comparison of the original study.
- **New:** a root-cause investigation combining a direct compute-budget ablation (ruling out under-sampling) with a three-part structural bottleneck taxonomy (capacity, traffic-concentration, and topological) applied to the floorplans' raw navigation graphs.
- **New:** an 18-floorplan synthetic corpus with independently controlled corridor topology, used to test the structural hypothesis under conditions the original five floorplans cannot provide, statistically confirming that variable count is the strongest univariate predictor of optimality gap overall, with corridor diameter (not bridge count, our initial hypothesis) a comparably strong structural predictor that adds explanatory information beyond variable count, replicated under both Neal and Hybrid.

## 2. Related Work

**Building evacuation networks and exit assignment.** Chalmet, Francis, and Saunders developed foundational network models for building evacuation in which occupants move through capacity-limited arcs toward exits. Kang, Jeong, and Kwun later formulated a closely related facility-final exit assignment problem, where rooms or other building subspaces are assigned to known routes leading to exterior exits. Their integer model keeps occupants associated with a facility together, while a linear variant allows splitting. This structure is an important classical predecessor to the present room-group formulation.

The NIST review by Kuligowski, Peacock, and Hoskins places route optimization within a broader evacuation-modeling landscape that may include pre-movement delay, individual behavior, smoke and fire effects, exit blockage, group movement, and validation against experiments. The present work addresses only the route-assignment layer.

**Capacity-, congestion-, and risk-aware routing.** Desmet and Gelenbe proposed capacity-based evacuation guidance with dynamic exit signs. Zhang et al. developed congestion-aware indoor evacuation routing using augmented-reality devices. Pedestrian bottleneck research shows exit throughput depends on geometry, crowd formation, and incoming flow rather than a single universal capacity value. Accordingly, the capacities used here are relative prototype values for optimization experiments, not empirically calibrated pedestrian flow rates.

**Classical path generation and direct shortest-path QUBOs.** Dijkstra's algorithm provides shortest paths on graphs with nonnegative edge weights, while A* uses a heuristic to guide search. Krauss and McCollum encode the shortest-path problem itself into a QUBO. The present two-stage design instead reduces the logical decision to selecting among already-valid routes, reserving quadratic interactions for system-level congestion and assignment.

**QUBO, traffic assignment, and quantum evacuation.** Lucas provides general Ising and QUBO constructions for many discrete optimization problems. Neukart et al. applied quantum annealing to traffic-flow optimization by selecting candidate routes while penalizing shared road segments. Shikanai et al. provide the closest recent comparison: a large-scale vehicle-evacuation formulation choosing among pre-generated candidate routes while balancing travel distance and route overlap under a one-route-per-vehicle constraint. The present project adapts that general route-selection structure to indoor building graphs and room-level occupant groups, weighting shared edges by room occupancy and normalizing load by modeled edge capacity.

**Exact and reference baselines for QUBO-formulated problems.** A recurring, explicitly acknowledged limitation across this literature — including the original version of the present study — is the absence of an exact classical reference baseline: results are often reported as best-observed energy across repeated solver runs, without an exact solver-side optimum for the corresponding constrained model. Here we use Google OR-Tools CP-SAT to optimize a scaled-integer reformulation of the distance-plus-congestion objective without embedding, chaining, or QUBO penalty tuning. CP-SAT supplies an `OPTIMAL` status and matching bound for that integer-scaled model; the selected assignment is then rescored under the original unpruned float64 objective. This provides a much stronger reference than solver-vs-solver comparison alone, while the effect of coefficient rounding on assignment ordering remains a limitation discussed below.

**Research gap and positioning.** Existing research has established network-flow evacuation models, facility-to-exit assignment, congestion-aware indoor routing, direct shortest-path QUBOs, quantum traffic assignment, and quantum evacuation-route selection, but has rarely combined a strong exact classical reference formulation, formal significance testing, and a controlled structural analysis of *why* certain floorplan topologies resist QUBO-based optimization. This paper addresses that intersection. It does not claim quantum advantage.

## 3. Problem Definition and Scope

Let a building be represented by a graph G=(V,K), where V contains navigation, room-start, doorway, and exit nodes, and K contains legal movement edges. Each edge has a positive distance and a positive relative capacity. Let R denote the set of rooms and E the set of designated exterior exits. For each pair (r,e), a single legal shortest route is precomputed and stored. Every occupant assigned to room r is treated as one indivisible group with occupancy p_r:

$$x_{r,e} \in \{0,1\}, \qquad r \in R,\ e \in E \tag{1}$$

The assignment must select exactly one exit route for every room, balancing total travel distance against concentration of large occupant groups on shared low-capacity edges. This is a static planning model; it computes neither a movement schedule nor an evacuation completion time. Assumptions, retained from the original study, include: all occupants in a room follow the same selected route; one candidate path is available per room-exit pair; occupancy and edge capacities remain fixed during a run; congestion is represented by simultaneous route overlap, not a time-resolved queue; and all designated exits are available.

## 4. Floorplan Graphs and Preprocessing

### 4.1 Wall-aware graph construction

The five benchmark floorplans were manually constructed as indoor navigation graphs, with room centers connecting to doorway nodes, doorway nodes connecting to corridor navigation points, and exit nodes connecting to the interior graph through legal openings. Edges crossing walls, leaving the building, or bypassing doors are prohibited.

**Table 1. Benchmark floorplans and logical problem sizes.**

| ID | Building type | Rooms | Exits | Variables | Nodes | Edges | Occupants |
|---|---|---:|---:|---:|---:|---:|---:|
| FP01 | Office | 12 | 5 | 60 | 173 | 245 | 100 |
| FP02 | School administration | 33 | 8 | 264 | 584 | 793 | 183 |
| FP03 | Dormitory | 28 | 9 | 252 | 571 | 792 | 65 |
| FP04 | Museum | 8 | 2 | 16 | 173 | 258 | 164 |
| FP05 | Clinic | 24 | 3 | 72 | 359 | 505 | 85 |

### 4.2 Route generation and validation

Dijkstra's algorithm computes the shortest legal path from every room-start node to every exit; A* independently verifies path-length agreement. The repository's automated test suite covers graph loading, node and edge validity, connectivity, doorway structure, room-to-exit reachability, route generation, floorplan consistency, and Dijkstra–A* agreement. At the time of this revision, with the 18-floorplan synthetic corpus added under the same auto-discovering test harness, the complete suite passes 49 of 49 tests (13 of 13 on the original five floorplans alone).

## 5. Capacity-Aware QUBO Formulation

The binary route variables are assembled into a BQM with linear and quadratic coefficients. The total energy is:

$$H(\mathbf{x}) = H_{\text{distance}}(\mathbf{x}) + H_{\text{congestion}}(\mathbf{x}) + H_{\text{assignment}}(\mathbf{x}) \tag{2}$$

**Normalized distance term:**

$$H_{\text{distance}}(\mathbf{x}) = \frac{1}{S_D}\sum_{r \in R}\sum_{e \in E} d_{r,e}\, x_{r,e} \tag{3}$$

$d_{r,e}$ is the length of the stored route from room $r$ to exit $e$; $S_D$ is a data-derived scale preventing raw distance magnitudes from dominating.

**Occupancy-weighted edge load:**

$$L_k(\mathbf{x}) = \sum_{r \in R}\sum_{e \in E} p_r\, I_{r,e,k}\, x_{r,e}, \qquad u_k(\mathbf{x}) = \frac{L_k(\mathbf{x})}{C_k} \tag{4}$$

$I_{r,e,k}$ equals one when route $(r,e)$ uses physical graph edge $k$; the prototype effective capacity is $C_k = 10 c_k$, where $c_k$ is the relative capacity stored in the floorplan's edge table.

**Quadratic congestion term:**

$$H_{\text{congestion}}(\mathbf{x}) = \frac{w_c}{S_C}\sum_{k \in K}\left(\frac{L_k(\mathbf{x})}{C_k}\right)^2, \qquad w_c = 5 \tag{5}$$

$S_C$ is a data-derived normalization scale. Squaring utilization creates both individual and pairwise costs: if two selected routes share edge $k$, their normalized loads generate a positive quadratic interaction. This term is a Gram-matrix quadratic in $\mathbf{x}$ (Section 6) — a fact central to this paper's exact-baseline contribution.

**Exactly-one assignment penalty:**

$$H_{\text{assignment}}(\mathbf{x}) = A \sum_{r \in R}\left(1 - \sum_{e \in E} x_{r,e}\right)^2 \tag{6}$$

Expanding, $A(1-\sum_e x_{r,e})^2 = A - A\sum_e x_{r,e} + 2A\sum_{e<f} x_{r,e}x_{r,f}$, assigning a negative linear bias to every route and a positive interaction between every pair of routes for the same room. Rather than fixing $A$ across instances, the largest positive marginal feasible route cost $M_{\max}$ is estimated and:

$$A = 1.5\,(M_{\max} + 0.25) \tag{7}$$

This penalty is recalculated per floorplan. Congestion-only interactions below $10^{-4}$ are pruned for QPU density reduction (assignment interactions are never pruned); the reported penalized-BQM energy therefore differs by a small, previously-documented amount from the exact, unpruned energy this paper's CP-SAT reference baseline reports.

## 6. Exact Solver Reference via Convex Quadratic Structure

### 6.1 Motivation

Every result in the original study is a *lowest energy observed* across repeated runs, not a certified optimum, except for FP04, whose 256 feasible assignments could be exhaustively enumerated. This leaves the absolute solution-quality question unresolved for four of five floorplans and is explicitly listed as a limitation in the original study.

### 6.2 The penalty method obscures a convex quadratic objective

Equation 6's role is purely to make the exactly-one-route-per-room constraint expressible inside an unconstrained BQM, as required by Neal, Hybrid, and QPU samplers. But the constraint itself, $\sum_{e} x_{r,e} = 1$ for every room, is a linear equality. And $H_{\text{congestion}}$ (Equation 5) is a sum of squared linear forms in $\mathbf{x}$ — equivalently, $\mathbf{x}^\top \mathbf{Q} \mathbf{x}$ for a Gram matrix $\mathbf{Q} = \mathbf{L}\mathbf{L}^\top$ built from the per-route normalized-load vectors — and a Gram matrix is positive semi-definite. The optimization problem underneath the QUBO reduction,

$$\min_{\mathbf{x} \in \{0,1\}^n} H_{\text{distance}}(\mathbf{x}) + H_{\text{congestion}}(\mathbf{x}) \quad \text{s.t.} \quad \sum_{e \in E} x_{r,e} = 1 \ \ \forall r \in R \tag{8}$$

therefore has a convex quadratic objective over a discrete binary feasible set. This removes the QUBO penalty term and embedding requirement from the classical reference formulation, although the feasible set remains combinatorial.

### 6.3 A per-edge CP-SAT formulation

A direct implementation expanding $\mathbf{x}^\top\mathbf{Q}\mathbf{x}$ into pairwise product terms scales quadratically in the number of routes — prohibitive for FP02's 264 routes. Instead, we introduce one integer variable per *edge* (not per route pair), $\text{load}_k = \sum_{r,e} \lfloor S \cdot p_r I_{r,e,k} / C_k \rceil\, x_{r,e}$ for an integer scale $S$, and a single squared variable $\text{sq}_k = \text{load}_k^2$ via a native multiplication constraint. This keeps the model size linear in $(|R|\cdot|E| + |K|)$, not quadratic in $|R|\cdot|E|$, and is what allows FP02 and FP03 — both too densely coupled to embed directly on the QPU — to solve in seconds via this route.

We use Google OR-Tools CP-SAT, an open-source, license-free constraint-programming solver — not an MIQP solver in the general sense, but sufficient for this integer-coefficient instance — so the reference baseline is independently reproducible without any commercial solver license. Because CP-SAT requires integer coefficients, normalized load coefficients are scaled and rounded before optimization. CP-SAT's `OPTIMAL` certificate therefore applies directly to this integer-scaled formulation. The selected assignment is then recomputed independently in float64 using the identical unpruned objective formula in Equations 3–5. This rescoring reports the original-objective energy of the CP-SAT-selected assignment, but by itself does not prove that coefficient rounding could never change assignment ordering under the unrounded objective; we therefore treat these values as a strong exact-solver reference rather than claiming a formal certificate for the original floating-point objective. The Validation checks below build confidence in the reformulation and rescoring, not in order-preservation under rounding, which remains an open item (see Limitations).

### 6.4 Validation

Two independent checks confirm correctness before any downstream result is trusted. First, for FP04, the CP-SAT solution rescored under the original objective is 1.5026583666…, matching the original study's exhaustive-enumeration ground truth to 10 decimal places. Second, applying the same objective-recomputation code to an *existing* saved Neal assignment (FP03) reproduces that assignment's own previously-reported unpruned energy exactly, byte-for-byte (0.5452529142969503 both sides) — confirming the reformulated objective is identical to, not merely similar to, the original.

Every one of the five benchmark floorplans, and all 18 synthetic floorplans, solved to CP-SAT status `OPTIMAL` for the integer-scaled formulation in under two seconds each.

## 7. Solver Methods

- **Classical path baselines.** Nearest-exit Dijkstra assigns every room to the shortest stored path; a greedy congestion-aware algorithm processes rooms in occupancy order, updating projected edge costs. Neither optimizes the same fixed candidate-route QUBO and both remain contextual comparators only (Appendix A).
- **Neal simulated annealing.** A fully classical Ocean sampler accepting the identical BQM representation as the quantum and Hybrid solvers. Each original benchmark run used 1,000 reads, 5,000 sweeps, and four seeds.
- **D-Wave Leap Hybrid.** `LeapHybridSampler` combines classical and quantum resources without requiring direct minor-embedding. Applied to all five floorplans and, in this revision, to all 18 synthetic floorplans as well.
- **Direct QPU execution.** `DWaveSampler` wrapped with `EmbeddingComposite` and `SpinReversalTransformComposite`, using solver `Advantage_system4`; 1,000 reads, four spin-reversal transforms, 20-microsecond anneal time, chain-strength prefactor 1.5. Embedding succeeded for FP01, FP04, and FP05 but not FP02 or FP03.
- **CP-SAT reference baseline (new).** Google OR-Tools CP-SAT applied to all 23 floorplans (five benchmark, 18 synthetic).

## 8. Experimental Design

Thirty independent benchmark runs were completed per solver-floorplan combination for the original five floorplans (Neal and Hybrid on all five; direct QPU on the three embeddable ones), yielding the 390-run dataset of the original study. This revision adds: (i) one CP-SAT reference solve per floorplan (23 total); (ii) a direct compute-budget ablation on Neal for FP02 and FP03; (iii) ten independent Neal and ten independent Hybrid runs on all 23 floorplans (230 Hybrid calls total, each at D-Wave's documented 3.0-second minimum time limit for problems under 1,024 variables) for formal significance testing; and (iv) full CP-SAT + Neal + Hybrid evaluation of an 18-floorplan synthetic corpus.

## 9. Results

### 9.1 Mean solution quality (original five floorplans)

Hybrid produced the lowest mean energy on four of five floorplans in the original 30-run benchmark, improving mean energy by 4.6–8.5% relative to Neal (Table 2), with all best assignments valid. These figures are retained from the original study and are the basis for the reference-gap comparison that follows.

**Table 2. Repeated-run solution metrics, mean ± sample standard deviation, n=30 (original study).**

| ID | Solver | Best energy | Distance | Congestion | Valid samples |
|---|---|---:|---:|---:|---:|
| FP01 | Neal | 0.7050 ± 0.0271 | 121.8 ± 6.0 | 195.8 ± 13.3 | 100.00% |
| FP01 | Hybrid | 0.6447 ± 0.0179 | 110.8 ± 4.2 | 181.3 ± 9.1 | 100.00% |
| FP02 | Neal | 0.6433 ± 0.0237 | 748.6 ± 27.7 | 1048.2 ± 140.2 | 100.00% |
| FP02 | Hybrid | 0.6136 ± 0.0199 | 720.4 ± 23.6 | 954.6 ± 128.9 | 100.00% |
| FP03 | Neal | 0.6059 ± 0.0240 | 595.3 ± 23.5 | 147.7 ± 13.1 | 100.00% |
| FP03 | Hybrid | 0.5589 ± 0.0241 | 551.2 ± 23.9 | 133.7 ± 11.4 | 100.00% |
| FP04 | Neal | 1.5027 ± 0.0000 | 60.0 ± 0.0 | 630.9 ± 0.0 | 100.00% |
| FP04 | Hybrid | 1.5027 ± 0.0000 | 60.0 ± 0.0 | 630.9 ± 0.0 | 100.00% |
| FP05 | Neal | 0.7937 ± 0.0317 | 321.8 ± 11.5 | 160.4 ± 10.4 | 100.00% |
| FP05 | Hybrid | 0.7381 ± 0.0325 | 305.2 ± 12.4 | 142.6 ± 9.4 | 100.00% |

### 9.2 Optimality gaps against the CP-SAT reference

Table 3 reports each floorplan's CP-SAT reference energy alongside the original 30-run best-observed energies. FP04's CP-SAT reference matches the previously-reported exact value exactly. FP01 and FP05, both embeddable on the QPU, show modest gaps (3–14%). FP02 and FP03 — precisely the two floorplans that could not be directly embedded on the QPU — show Neal and Hybrid landing **94–125%** above the CP-SAT reference energy: more than double the reference on the hardest cases, a gap invisible in Table 2's solver-vs-solver comparison, where FP02 and FP03 do not stand out as unusual at all.

**Table 3. CP-SAT reference energy vs. best-observed energy (30-run benchmark), with relative gap.** Neal/Hybrid values are the unpruned objective recomputed from the winning assignment, matching the CP-SAT reference's basis exactly — not the pruned-BQM search energy, which differs by a small (<0.4%) amount.

| ID | CP-SAT reference | Neal best | Neal gap | Hybrid best | Hybrid gap |
|---|---:|---:|---:|---:|---:|
| FP01 | 0.581344 | 0.636840 | 9.55% | 0.600349 | **3.27%** |
| FP02 | 0.261443 | 0.587613 | 124.76% | 0.577324 | **120.82%** |
| FP03 | 0.256160 | 0.545253 | 112.86% | 0.497750 | **94.31%** |
| FP04 | 1.502658 | 1.502658 | 0.00% | 1.502658 | 0.00% |
| FP05 | 0.615057 | 0.704015 | 14.46% | 0.655631 | **6.60%** |

For FP03 specifically, the practical severity of this gap is best appreciated physically: the CP-SAT reference assignment (distance 254.25, raw congestion 11.85) is barely worse than the trivial, congestion-blind nearest-exit-Dijkstra baseline (distance 250.75, raw congestion 64.49, Appendix A), while Neal and Hybrid's reported "100% valid" solutions (distance 551–595, raw congestion 134–148) are simultaneously worse than that trivial baseline on *both* distance and congestion — a strictly dominated solution that a validity check alone cannot detect, since validity only verifies the exactly-one constraint, not solution quality.

### 9.3 Statistical significance

The original study explicitly notes the absence of formal significance testing. We apply Mann-Whitney U (not paired Wilcoxon: Neal's local seeds and Hybrid's server-side randomness are independent, not paired samples) to the 30-run distributions, Bonferroni-corrected across five floorplans (α=0.01). Hybrid is significantly better than Neal on FP01, FP03, and FP05 (p<10⁻⁵) and on FP02 (p≈1.02×10⁻⁵, significant after Bonferroni correction though just above the 10⁻⁵ mark); FP04 shows a technically significant but practically meaningless p=1.7×10⁻¹⁴, reflecting floating-point-noise-level differences between two distributions that both reach the exact optimum on every run — a concrete illustration of why p-values must be read alongside effect size, not alone. Per-run (not just best-run) optimality gaps against the CP-SAT reference show neither solver ever reaches the reference energy across 30 independent runs on FP02 or FP03 (closest approach: Neal 124.76%, Hybrid 120.82% on FP02).

### 9.4 Root-cause investigation: ruling out compute budget

FP02 and FP03's large gaps could plausibly reflect an under-provisioned, fixed compute budget (1,000 reads, 5,000 sweeps for every floorplan regardless of its 16-to-264-variable range) rather than any structural property. We test this directly: rerunning Neal on FP02 and FP03 with 5×, 20×, and 100× the original sweep count (up to 500,000 sweeps), at 200 total reads per setting (50 reads across each of four seeds) rather than the original benchmark's 1,000 — so this ablation tests sensitivity to sweep count specifically, not a controlled like-for-like increase in total compute budget. The gap does *not* close — both floorplans oscillate in roughly the same range regardless of sweep count (FP02: 153–163%; FP03: 110–161%, non-monotonically), ruling out under-sampling via sweep count alone as the explanation and reframing the question from *how much* compute is needed to *what about the landscape traps the search* in the first place.

### 9.5 Geometric and topological bottleneck analysis

We quantify each floorplan's raw navigation graph (independent of the QUBO) directly from its node and edge tables, defining bottlenecks three complementary ways, since no single measure captures the concept: (i) *capacity bottleneck* — the paper's own worst-case simultaneous per-edge utilization; (ii) *traffic-concentration bottleneck* — how many distinct candidate routes use a given edge at all, independent of capacity; (iii) *structural bottleneck* — bridge edges and articulation points in the raw navigation graph, with a *critical bridge* defined as one lying on the recorded path of two or more distinct rooms.

FP02 and FP03 have roughly 2–25× more bridges and critical bridges than FP01 and FP04, and the most capacity-bottleneck edges by a wide margin (Table 4); against FP05 specifically, the gap is far narrower (1.3–1.5×), so bridge count alone does not cleanly separate FP02/FP03 from every other floorplan. FP03 (dormitory) has a corridor-subgraph diameter of 40 hops — roughly double every other floorplan — consistent with a long single-spine hallway layout.

**Table 4. Structural comparison across the five benchmark floorplans.**

| ID | Rooms | Hallway nodes | Route hops (mean/max) | Corridor diam. | Bridges | Critical bridges |
|---|---:|---:|---|---:|---:|---:|
| FP01 | 12 | 34 | 15.4 / 25 | 21 | 34 | 13 |
| FP02 | 33 | 107 | 28.6 / 48 | 22 | 70 | 33 |
| FP03 | 28 | 204 | 27.5 / 49 | 40 | 81 | 41 |
| FP04 | 8 | 8 | 12.6 / 19 | 5 | 3 | 2 |
| FP05 | 24 | 66 | 19.2 / 32 | 22 | 54 | 22 |

### 9.6 An 18-floorplan synthetic corpus: confirming and correcting the structural hypothesis

Five benchmark floorplans confound topology with size, room/exit ratio, and building type simultaneously, and cannot statistically confirm a structural hypothesis on their own. We generate 18 additional floorplans, in the identical CSV schema as FP01–FP05, spanning three *independently controlled* corridor topologies at three sizes (10, 20, 30 rooms) and two random seeds (occupancy/capacity only; topology is deterministic given size):

- **Linear**: a single corridor spine, rooms along its length. Maximum structural bottleneck by design.
- **Tree**: a branching spine, rooms on short branches. A tree graph has zero cycles, so *every* edge is technically a bridge, but each is shared by only the few rooms on its own branch.
- **Loop**: corridor forms a single ring, rooms attached around it. Minimal structural bottleneck — the ring gives every hallway edge an alternate path.

All 18 pass the repository's own auto-discovering connectivity, door-degree, and reachability test suite unmodified, and all 18 solve to CP-SAT status `OPTIMAL` for the integer-scaled reference formulation in under two seconds each.

#### 9.6.1 Structure predicts difficulty, but not the way we first hypothesized

Combining all 23 floorplans (five benchmark and 18 synthetic, n=23), every candidate structural predictor correlates significantly with both solvers' 10-repeat mean optimality gap (Table 5). Raw variable count is the strongest univariate predictor (r=0.865 Neal, 0.873 Hybrid), with corridor diameter close behind (r=0.837 Neal, 0.823 Hybrid) — both well ahead of every bridge-based measure. Critical-bridge count, our original working hypothesis, trails at r≈0.70 for both solvers; plain bridge count trails further still (r≈0.60–0.62).

**Table 5. Full correlation of each structural predictor with the 10-repeat mean optimality gap, n=23.**

| Predictor | Neal r | Neal p | Hybrid r | Hybrid p |
|---|---:|---:|---:|---:|
| n_variables | **0.865** | 9.9×10⁻⁸ | **0.873** | 5.5×10⁻⁸ |
| corridor_diameter_hops | 0.837 | 6.3×10⁻⁷ | 0.823 | 1.4×10⁻⁶ |
| route_hops_mean | 0.736 | 6.2×10⁻⁵ | 0.761 | 2.5×10⁻⁵ |
| structural_critical_bridge_count | 0.702 | 1.9×10⁻⁴ | 0.700 | 2.0×10⁻⁴ |
| structural_bridge_count | 0.622 | 1.5×10⁻³ | 0.603 | 2.4×10⁻³ |
| capacity_bottleneck_edge_count | 0.702 | 1.9×10⁻⁴ | 0.743 | 4.9×10⁻⁵ |
| traffic_bottleneck_top1_share | 0.713 | 1.3×10⁻⁴ | 0.699 | 2.1×10⁻⁴ |

The interesting result is not that corridor diameter beats size outright — it does not, slightly, for either solver — but that it is essentially *as informative as size while capturing something size does not*, confirmed directly by the regression below. Critically, our original working hypothesis — that critical-bridge count drives difficulty — does not order the three controlled topologies correctly. At matched room counts, Tree has 5–6× more critical bridges than Loop (21 vs. 4 at 20 rooms; 29 vs. 6 at 30 rooms) yet a *smaller* optimality gap both times (Table 6). Corridor diameter and mean route length, by contrast, track the observed difficulty pattern more consistently — though not perfectly: at 10 rooms the order is Loop (4) < Tree (8) < Linear (9), and at 20 rooms Tree and Loop tie at diameter 8, so Tree < Loop < Linear is a general trend across the corpus rather than a strict ordering at every size.

**Table 6. Illustrative subset: topology, structure, and 10-repeat mean Hybrid optimality gap.**

| Topology | Rooms | Critical bridges | Corridor diameter | Hybrid gap (mean of 2 seeds) |
|---|---:|---:|---:|---:|
| Loop | 20 | 4 | 8 | 14.7% |
| Tree | 20 | 21 | 8 | 6.0% |
| Loop | 30 | 6 | 12 | 55.0% |
| Tree | 30 | 29 | 10 | 22.0% |

This is a genuine, physically interpretable correction rather than a failure to confirm: a tree's bridges are each shared by only the handful of rooms on that specific short branch, while a loop routes *every* room's traffic through the same single ring, concentrating congestion onto shared capacity regardless of how many technically-non-redundant edges exist. Route/corridor length is the better proxy for how much combinatorial interaction accumulates per room's routing decision.

Multiple regression confirms corridor diameter adds substantial explanatory power beyond raw size: partial correlation controlling for variable count is r=0.727 (p=8.5×10⁻⁵), and R² rises from 0.749 (variable count alone) to 0.882 with corridor diameter added for Neal's 10-repeat mean gap (0.762 to 0.877 for Hybrid's) — roughly six times the additional variance explained by critical-bridge count alone in the same regression framework (+0.021 and +0.018 R² respectively).

#### 9.6.2 Replication under Hybrid, with proper significance testing

Repeating this analysis with ten independent Neal *and* ten independent Hybrid runs on all 23 floorplans (230 Hybrid calls total) allows both a direct significance test and a check that the structural finding is not an artifact of Neal's particular search dynamics. Hybrid's mean gap is smaller than Neal's in 18 of 23 floorplans. Solver distributions differ significantly (Bonferroni-corrected across 23 tests) in 16 of 23 floorplans — not necessarily the same 16 where Hybrid was better; Hybrid is both lower in mean gap *and* Bonferroni-significant in 11 of 23. This still extends the original study's Hybrid-outperforms-Neal finding to the full synthetic corpus, with the more precise figure being the 11/23 both-and count. Corridor diameter predicts Hybrid's gap (r=0.823, p=1.4×10⁻⁶) essentially as well as it predicts Neal's (r=0.837, p=6.3×10⁻⁷): the structural mechanism is not solver-specific.

### 9.7 **[v4]** Correcting a geometry artifact: diagonal shortcut edges in the synthetic corpus

> **Status: complete.** Both Neal (free, local) and Hybrid (180 calls, using the corresponding author's own D-Wave Leap account) have been re-run on the diagonal-fixed corpus.

Every edge `scripts/expansion/generate_synthetic_floorplan.py` creates is assigned `distance=1.0`, regardless of the angle it is drawn at. This is harmless for an axis-aligned edge, but three sites produced edges that moved diagonally — both in x and y in a single hop: Loop's door-to-corridor edge (one per room), Loop's ring-to-exit edge (one per exit), and Tree's spine-to-first-branch-node edge (one per branch). A real, wall-respecting corridor cannot cut a corner this way; reaching the same point axis-aligned requires two hops, not one. Every such edge was therefore a one-hop shortcut not available to the five manually constructed benchmark layouts, whose graphs are hand-built to be wall-aware. Linear's topology never produced a diagonal edge and is an unaffected control.

Fixed by routing each affected connection through an intermediate axis-aligned elbow node (turn the corner in two hops instead of cutting through it), verified programmatically afterward that zero diagonal edges remain in any of the three topologies, and regenerated all 18 synthetic floorplans under new `_V2` identifiers (e.g. `SYN_LOO_20_S1_V2`), leaving the original 18 untouched on disk for direct comparison.

#### 9.7.1 Structural metrics shift for Loop and Tree, not Linear

**Table 7. Corridor diameter and route hop length, original synthetic corpus vs. diagonal-fixed V2, seed S1** (S2 moves identically since structure is seed-independent).

| Floorplan | Corridor diam. (old → V2) | Route hops mean (old → V2) | Bridges (old → V2) |
|---|---|---|---|
| Linear-10 | 9 → 9 | 7.5 → 7.5 | 31 → 31 |
| Linear-20 | 19 → 19 | 10.6 → 10.6 | 63 → 63 |
| Linear-30 | 29 → 29 | 13.7 → 13.7 | 95 → 95 |
| Loop-10 | 4 → 6 | 4.8 → 6.8 | 22 → 34 |
| Loop-20 | 8 → 10 | 6.9 → 8.9 | 44 → 68 |
| Loop-30 | 12 → 14 | 8.9 → 10.9 | 66 → 102 |
| Tree-10 | 8 → 10 | 7.3 → 8.3 | 37 → 41 |
| Tree-20 | 8 → 10 | 6.6 → 7.6 | 69 → 77 |
| Tree-30 | 10 → 12 | 7.6 → 8.6 | 105 → 121 |

Linear is byte-for-byte unaffected, as expected. Loop and Tree both gain exactly the elbow-node count the fix predicts (Loop: one per room plus one per exit; Tree: one per branch), confirmed directly against node/edge counts before recomputing anything else. Notably, Tree-20 and Loop-20's corridor diameter — tied at 8 in the original corpus, the specific pairing Section 9.6.1 uses to argue bridge count doesn't order difficulty correctly — remain *exactly tied* after the fix, now at 10.

#### 9.7.2 Optimality gaps drop for Loop and Tree, Linear unchanged — both solvers

**Table 8. 10-repeat mean optimality gap against the CP-SAT reference, original corpus vs. diagonal-fixed V2, both solvers** (energies recomputed unpruned throughout).

| Floorplan | Old Neal → V2 Neal | Δ | Old Hybrid → V2 Hybrid | Δ |
|---|---|---:|---|---:|
| Linear-20-S1 | 51.78 → 51.79 | +0.01 | 32.59 → 35.96 | +3.37 |
| Linear-20-S2 | 49.48 → 49.52 | +0.04 | 34.92 → 32.64 | −2.28 |
| Linear-30-S1 | 128.15 → 128.83 | +0.68 | 103.58 → 99.17 | −4.41 |
| Linear-30-S2 | 132.35 → 133.03 | +0.68 | 103.58 → 102.09 | −1.49 |
| Loop-20-S1 | 23.27 → 17.32 | −5.95 | 15.76 → 10.53 | −5.23 |
| Loop-20-S2 | 22.40 → 16.76 | −5.64 | 13.59 → 11.46 | −2.13 |
| Loop-30-S1 | 69.28 → 48.16 | −21.12 | 56.92 → 38.03 | −18.89 |
| Loop-30-S2 | 68.17 → 48.75 | −19.42 | 53.03 → 37.39 | −15.64 |
| Tree-20-S1 | 8.50 → 6.15 | −2.35 | 6.07 → 3.93 | −2.14 |
| Tree-20-S2 | 9.82 → 7.20 | −2.62 | 5.84 → 4.57 | −1.27 |
| Tree-30-S1 | 29.14 → 22.49 | −6.65 | 23.40 → 17.01 | −6.39 |
| Tree-30-S2 | 26.40 → 22.42 | −3.98 | 20.58 → 18.10 | −2.48 |

Linear moves within ordinary run-to-run noise under both solvers (−2.28 to +3.37pp), while Loop and Tree drop substantially and consistently under both, Loop far more than Tree (up to −21.12pp Neal / −18.89pp Hybrid vs. up to −6.65pp Neal / −6.39pp Hybrid), matching the asymmetry in how many diagonal shortcuts each topology had (one per room in Loop; one per branch in Tree). The same pattern appearing under two independently-run solvers is strong evidence the diagonal-edge artifact was inflating measured difficulty specifically for the topologies that had it, not solver-specific noise.

#### 9.7.3 The core finding survives, and strengthens — both solvers

Combining the unchanged 5 benchmark floorplans with the diagonal-fixed 18-floorplan V2 corpus (n=23) and repeating the correlation analysis behind Table 5:

**Table 9. Predictor correlation with 10-repeat mean gap, original 23-instance corpus (Table 5) vs. V2 diagonal-fixed 23-instance corpus, both solvers.**

| Predictor | Old Neal r | V2 Neal r | Old Hybrid r | V2 Hybrid r |
|---|---:|---:|---:|---:|
| n_variables | 0.865 | 0.826 | 0.873 | 0.836 |
| corridor_diameter_hops | 0.837 | **0.868** | 0.823 | **0.853** |
| route_hops_mean | 0.736 | 0.765 | 0.761 | 0.800 |
| capacity_bottleneck_edge_count | 0.702 | 0.712 | 0.743 | 0.763 |
| traffic_bottleneck_top1_share | 0.713 | 0.697 | 0.699 | 0.680 |
| structural_critical_bridge_count | 0.702 | 0.586 | 0.700 | 0.585 |
| structural_bridge_count | 0.622 | 0.457 | 0.603 | 0.436 |

Corridor diameter is now the single strongest predictor for *both* solvers, ahead of raw variable count in both cases — the opposite direction from a concern that removing an artifact might weaken the finding. The bridge-based measures, already the weakest predictors and already rejected as the primary explanation, get weaker still, again for both solvers. The Neal regression result: R² from variable count alone is 0.682 (V2) vs. 0.749 (old); adding corridor diameter raises it to 0.857 (V2) vs. 0.882 (old); partial correlation r=0.742, p=5.0×10⁻⁵ (V2) vs. r=0.727, p=8.5×10⁻⁵ (old).

#### 9.7.4 Hybrid-outperforms-Neal finding: essentially unchanged

Repeating Section 9.6's Mann-Whitney significance test (α=0.05, Bonferroni-corrected across 23 instances) on the V2 corpus: Hybrid's mean gap is lower than Neal's in **17 of 23** instances (old: 18 of 23), Bonferroni-significant in **11 of 23** (old: 16 of 23), and both lower *and* significant in **10 of 23** (old: 11 of 23). The headline comparative claim is essentially preserved — within one instance of the original counts on every measure — confirming the diagonal-edge bug affected absolute gap magnitude and the structural-predictor analysis, but not the solver-vs-solver comparison itself.

### 9.8 Direct-QPU feasibility and embedding

Direct-QPU performance remains strongly instance-dependent, retained from the original study: FP04 reproduced the exact optimum with 78.78% mean valid-sample rate; FP01 and FP05 required chains up to 9 and 12 physical qubits per logical variable respectively, with valid-sample rates below 1%; FP02 and FP03 could not be embedded at all. Given the finding that the same two floorplans are also the hardest for *classical* optimization once measured against the CP-SAT reference, embedding difficulty and solution-quality difficulty for this formulation appear to share a common structural origin (corridor diameter) rather than being independent failure modes of the quantum-specific pipeline.

## 10. Discussion

### 10.1 A strong reference baseline changes the empirical picture, not just its precision

The original study's central comparative claim — Hybrid outperforms Neal — survives and is now statistically confirmed. But the *absolute* quality claim it could not make (how good are these solutions, really?) changes substantially once a CP-SAT reference exists: two of five floorplans were, in fact, roughly twice the reference energy in the best saved annealing assignments, a finding a solver-vs-solver comparison structurally cannot surface, since both solvers can simultaneously be far from a stronger classical reference while one still beats the other. This is a general methodological point beyond this specific evacuation formulation: reporting only relative solver comparisons on QUBO-formulated problems, without an exact or reference baseline wherever the underlying combinatorial structure permits one, risks reporting precise but potentially misleading conclusions about absolute solution quality.

### 10.2 On being wrong in a useful way

Our first structural hypothesis (bridge/bottleneck-edge count) was reasonable, motivated directly by the paper's own QPU-embedding-density finding, and wrong in a specific, informative way: it does not order our own controlled synthetic topologies correctly. Building the synthetic corpus specifically to stress-test that hypothesis, rather than stopping at the five benchmark floorplans' correlational support for it, is what exposed the correction. We report this as a case study in the value of controlled synthetic ablations over correlational analysis alone: critical-bridge count's correlation with optimality gap is itself statistically significant and reasonably strong (r=0.70–0.73 across both solvers, p<0.0002) — convincing enough on its own to stop there — yet the controlled topology comparison shows it still gets the underlying mechanism wrong.

### 10.3 Why corridor length, mechanistically

A longer route through the network touches more edges, and each additional edge is a potential point of interaction with every other room's route through the congestion term's Gram-matrix structure. Longer corridors therefore accumulate more combinatorial coupling per room's single binary routing decision than a purely topological bridge count reflects, since a bridge shared by only two nearby rooms contributes far less coupling than a long shared corridor spine touched by every room in the building.

### 10.4 Interpretation of the congestion objective

Retained from the original study: the squared-utilization term is a surrogate cost. It does not simulate arrival times, queues, pedestrian speed, or crowd dynamics. A lower congestion objective describes a more distributed static assignment under the prototype capacity model, not a proven reduction in evacuation completion time.

## 11. Limitations

- The model remains static, with no time dimension, walking speed, queue, smoke, fire, or dynamically changing hazards.
- All occupants in a room remain one indivisible group; only one precomputed candidate path exists per room-exit pair.
- Edge capacities are relative prototype values, not calibrated pedestrian throughput measurements.
- CP-SAT certifies the integer-scaled reformulation used for optimization. The returned assignment is rescored under the original float64 objective, but the present analysis does not prove that coefficient rounding preserves the exact assignment ordering of the unrounded objective on every instance.
- A strong CP-SAT reference baseline now exists for all 23 floorplans studied (five benchmark, 18 synthetic) — resolving the original study's single-instance-only limitation — but the benchmark-floorplan corpus remains five manually constructed layouts, five building types; the synthetic corpus's controlled topologies are not a substitute for a larger, independently-sourced real-building sample.
- The synthetic generator connects rooms directly to their door without an interior room-tile grid (unlike the benchmark floorplans), by design, to isolate corridor-network structure — this should not bias the corridor-diameter finding itself, but means the synthetic corpus's absolute route-hop magnitudes are not directly comparable to the benchmark floorplans', only their relative ordering within-corpus.
- Each of the 18 synthetic floorplans is a distinct optimization instance: occupancy and capacity are redrawn per seed, which changes the QUBO's congestion coefficients and therefore the actual assignment problem solved and its resulting solver gap, not merely its energy value. The structural predictors (corridor diameter, bridge count, etc.), however, are properties of the navigation graph alone and are identical for both seeds of a given topology/size, so those specific structural comparisons draw on 9 distinct graph configurations, each evaluated under two independently-drawn occupancy/capacity conditions, rather than 18 structurally independent layouts. Reassuringly, this does not appear to be inflating the reported associations: restricting to the 14 structurally-unique instances (five benchmark, nine synthetic) leaves both the corridor-diameter correlation and the corridor-diameter/route-hop-length correlation unchanged to three decimal places — but p-values computed against the full n=23 should still be read with the repeated structures in mind.
- Corridor diameter and mean route-hop length are correlated with each other (r=0.801 across all 23 floorplans; r=0.801 also when restricted to the 14 structurally-unique instances) and not yet fully statistically separated; a synthetic sweep varying one independently of the other would sharpen this further.
- Hybrid repeat count on the full 23-floorplan corpus (ten runs) is lower than the original study's 30-run granularity on the five benchmark floorplans, a deliberate compromise against D-Wave Leap solver-time quota (approximately 12 minutes of Hybrid solver time for the 230 calls alone, at the platform's documented 3.0-second minimum time limit for problems under 1,024 variables).
- **[v4 — confirmed, Neal side]** Unlike Table 3, the 10-repeat Neal/Hybrid energies behind Tables 5, 6, and the appendix (Section 9.6) are the pruned-BQM search energy, not the independently-recomputed unpruned objective. Section 9.7 recomputed the true unpruned energy directly (not just spot-checked) across all 18 regenerated floorplans' Neal runs: maximum difference 0.68 percentage points, consistent with the original spot-check (max 0.26%) and the 5-floorplan figure (<0.4%). Confirmed negligible for Neal; the Hybrid side (230 calls) on the *original* corpus has still not been recomputed, since doing so on that corpus specifically costs D-Wave Leap quota (the V2 corpus's Hybrid side has been recomputed, see 9.7.2–9.7.4).
- **[v4 — resolved]** The synthetic generator's Loop and Tree topologies included some short non-axis-aligned (diagonal) connector edges that were, in fact, genuine one-hop shortcuts (every edge is weighted `distance=1.0` regardless of angle, so a diagonal hop covered more net displacement than an axis-aligned one could in a single hop). Root-caused, fixed (routed through an axis-aligned elbow node instead), and the corpus regenerated as `_V2` (Section 9.7); zero diagonal edges remain, verified programmatically. Both Neal and Hybrid were re-run on the corrected corpus (180 Hybrid calls); this measurably changed structural metrics and both solvers' gaps for Loop and Tree (Tables 7, 8), while the corridor-diameter finding and the Hybrid-outperforms-Neal finding both survive. The paper's main tables (5, 6, appendix) still show the originally-published, diagonal-affected numbers; Section 9.7 is where the corrected numbers currently live pending a decision on whether to replace them outright in a future version.
- The experiments do not establish quantum advantage, real-time deployment readiness, or real-world evacuation performance.

## 12. Future Work

**[v4 — done]** The diagonal-edge correction (Section 9.7) is now complete for both solvers. The remaining decision is whether to replace Tables 5, 6, and the appendix outright with the V2 numbers in a future version, versus keeping both corpora side by side as this draft does.

The next-highest-priority extension, retained from the original study, remains empirical and simulation-based validation of the capacity model against a validated evacuation simulator or controlled pedestrian studies. Beyond that, this revision's findings motivate: (i) verifying the CP-SAT integer scaling against the unrounded objective with an order-preservation proof, exact rational formulation, or another exact continuous-coefficient method; (ii) a synthetic sweep varying corridor diameter independently of route-hop count and room/exit ratio, to isolate the structural mechanism further; (iii) applying the same reference-baseline methodology to other QUBO-formulated routing problems in the reviewed literature, to test whether the same embedding-difficulty/solution-quality correlation generalizes beyond evacuation routing; (iv) an independently-sourced real-building corpus (e.g. the Modified Swiss Dwellings dataset, considered but not used in the original study) annotated with the same wall-aware graph pipeline, to test whether corridor diameter predicts difficulty on buildings this project did not design; and (v) dynamic hazard layers connecting the static assignment framework to risk-aware routing while preserving the graph-validation pipeline.

## 13. Conclusion

This paper extends a capacity-aware indoor evacuation-route assignment QUBO study, originally reporting best-observed solver energies across 390 runs on five floorplans, with a strong CP-SAT reference baseline, formal significance testing, and a controlled structural investigation. Reformulating the QUBO's penalty-method constraint as a native linear equality reveals the underlying problem is convex, letting a general-purpose, license-free CP-SAT solver reach status `OPTIMAL` for the integer-scaled formulation of every floorplan — including the two too dense to embed on the QPU — in under two seconds each. Measured against these reference energies, Neal and D-Wave Hybrid are roughly twice the reference energy on exactly those two floorplans, a finding invisible in the original solver-vs-solver comparison. A direct compute-budget ablation rules out under-sampling as the sole explanation; a controlled 18-floorplan synthetic corpus, built specifically to test and, ultimately, correct our own initial structural hypothesis, statistically confirms that variable count is the strongest univariate predictor of solver difficulty overall, with corridor diameter — not bridge/bottleneck-edge count — a comparably strong structural predictor that adds explanatory information beyond variable count, replicated under both classical and hybrid quantum solvers with Bonferroni-corrected Mann-Whitney testing. The result is a reproducible evacuation-QUBO workflow with a substantially stronger classical reference than prior work in this line, and an empirically grounded, statistically confirmed, and self-corrected account of what makes a floorplan hard for current annealing-based solvers to route well.

## Acknowledgments

The authors thank the Machine Perception and Cognitive Robotics Laboratory at Florida Atlantic University for providing the instructional framework and access to quantum-optimization resources.

## References

- Occupational Safety and Health Administration, "Evacuation Plans and Procedures eTool: Emergency Action Plan — Evacuation Elements," U.S. Department of Labor. Accessed: Jul. 31, 2026.
- L. G. Chalmet, R. L. Francis, and P. B. Saunders, "Network models for building evacuation," *Management Science*, vol. 28, no. 1, pp. 86–105, 1982.
- J. Kang, I. J. Jeong, and J. B. Kwun, "Optimal facility-final exit assignment algorithm for building complex evacuation," *Computers & Industrial Engineering*, vol. 85, pp. 169–176, 2015.
- E. D. Kuligowski, R. D. Peacock, and B. L. Hoskins, *A Review of Building Evacuation Models*, 2nd ed., NIST Technical Note 1680, 2010.
- A. Desmet and E. Gelenbe, "Capacity based evacuation with dynamic exit signs," in *Proc. IEEE Int. Conf. Pervasive Computing and Communications Workshops*, 2014, pp. 332–337.
- Z. Zhang, H. Liu, Z. Jiao, Y. Zhu, and S.-C. Zhu, "Congestion-aware evacuation routing using augmented reality devices," in *Proc. IEEE Int. Conf. Robotics and Automation*, 2020, pp. 2798–2804.
- R. Ye, J. Li, H. Lu, J. Wang, Y. Pan, and Y. Wang, "A study on the arch mechanism of pedestrian evacuation and congestion alleviation strategies at building exits," *Journal of Building Engineering*, vol. 88, art. 109159, 2024.
- E. W. Dijkstra, "A note on two problems in connexion with graphs," *Numerische Mathematik*, vol. 1, pp. 269–271, 1959.
- P. E. Hart, N. J. Nilsson, and B. Raphael, "A formal basis for the heuristic determination of minimum cost paths," *IEEE Transactions on Systems Science and Cybernetics*, vol. 4, no. 2, pp. 100–107, 1968.
- T. Krauss and J. McCollum, "Solving the network shortest path problem on a quantum annealer," *IEEE Transactions on Quantum Engineering*, vol. 1, pp. 1–12, 2020.
- A. Lucas, "Ising formulations of many NP problems," *Frontiers in Physics*, vol. 2, art. 5, 2014.
- F. Neukart, G. Compostella, C. Seidel, D. von Dollen, S. Yarkoni, and B. Parney, "Traffic flow optimization using a quantum annealer," *Frontiers in ICT*, vol. 4, art. 29, 2017.
- R. Shikanai, R. Haba, Y. Okazaki, K. Matsumoto, and M. Ohzeki, "Large-scale evacuation route optimization leveraging sampling diversity in quantum annealing," *Scientific Reports*, 2026.
- C. van Engelenburg, F. Mostafavi, E. Kuhn, Y. Jeon, M. Franzen, M. Standfest, J. van Gemert, and S. Khademi, "MSD: A benchmark dataset for floor plan generation of building complexes," in *Computer Vision – ECCV 2024*, LNCS 15116, pp. 60–75, 2025.
- D-Wave Quantum Inc., "Minor-Embedding: Best Practices," D-Wave Quantum Computing Products Documentation. Accessed: Jul. 31, 2026.
- L. Perron and V. Furnon, "OR-Tools," Google, version 9.x, 2024. https://developers.google.com/optimization
- H. B. Mann and D. R. Whitney, "On a test of whether one of two random variables is stochastically larger than the other," *The Annals of Mathematical Statistics*, vol. 18, no. 1, pp. 50–60, 1947.
- P. Virtanen et al., "SciPy 1.0: fundamental algorithms for scientific computing in Python," *Nature Methods*, vol. 17, pp. 261–272, 2020.
- A. Hagberg, P. Swart, and D. S Chult, "Exploring network structure, dynamics, and function using NetworkX," in *Proc. 7th Python in Science Conference*, 2008, pp. 11–15.

## Appendix A: Contextual Classical Routing Metrics

Table 10 reports deterministic route metrics illustrating the distance-congestion tradeoff; these do not optimize the same fixed candidate-route QUBO and are not exact energy baselines.

**Table 10. Deterministic routing metrics under the prototype capacity model.**

| ID | Method | Distance | Congestion | Overloaded edges | Max utilization |
|---|---|---:|---:|---:|---:|
| FP01 | Nearest-exit Dijkstra | 96.50 | 176.463 | 9 | 1.950 |
| FP01 | Greedy congestion-aware | 110.00 | 166.581 | 10 | 1.400 |
| FP02 | Nearest-exit Dijkstra | 317.50 | 319.976 | 14 | 1.800 |
| FP02 | Greedy congestion-aware | 385.50 | 290.228 | 7 | 1.800 |
| FP03 | Nearest-exit Dijkstra | 250.75 | 64.494 | 1 | 1.600 |
| FP03 | Greedy congestion-aware | 258.25 | 57.660 | 0 | 1.000 |
| FP04 | Nearest-exit Dijkstra | 60.00 | 630.890 | 24 | 3.467 |
| FP04 | Greedy congestion-aware | 63.50 | 645.438 | 21 | 3.667 |
| FP05 | Nearest-exit Dijkstra | 257.15 | 115.651 | 3 | 1.400 |
| FP05 | Greedy congestion-aware | 277.95 | 111.385 | 3 | 1.400 |

## Appendix B: Synthetic Corpus Specification

Room occupancy is drawn uniformly from [2,25] and edge capacities from small integer ranges matching the benchmark floorplans' scale (see the generator script, `scripts/expansion/generate_synthetic_floorplan.py`, for exact generation logic). Structural properties (Table 11) are deterministic given topology and size, not affected by the random seed, so are listed once per topology-size combination; CP-SAT reference energies and solver gaps (Table 12) vary by seed (occupancy/capacity draw) and are listed for both.

**Table 11. Synthetic corpus structural properties: 3 topologies × 3 sizes (seed-independent).**

| Topology | Rooms | Exits | Variables | Corridor diam. | Bridges | Crit. bridges |
|---|---:|---:|---:|---:|---:|---:|
| Linear | 10 | 2 | 20 | 9 | 31 | 11 |
| Linear | 20 | 4 | 80 | 19 | 63 | 23 |
| Linear | 30 | 6 | 180 | 29 | 95 | 35 |
| Tree | 10 | 2 | 20 | 8 | 37 | 13 |
| Tree | 20 | 4 | 80 | 8 | 69 | 21 |
| Tree | 30 | 6 | 180 | 10 | 105 | 29 |
| Loop | 10 | 2 | 20 | 4 | 22 | 2 |
| Loop | 20 | 4 | 80 | 8 | 44 | 4 |
| Loop | 30 | 6 | 180 | 12 | 66 | 6 |

**Table 12. Synthetic corpus full results, all 18 floorplans (both seeds): CP-SAT reference energy and 10-repeat mean optimality gap for each solver.**

| Topology | Rooms/Seed | CP-SAT reference | Neal gap (mean) | Hybrid gap (mean) |
|---|---|---:|---:|---:|
| Linear | 10 / S1 | 1.1940 | 0.00% | 0.00% |
| Linear | 10 / S2 | 1.2189 | −0.00% | 0.00% |
| Linear | 20 / S1 | 0.3971 | 51.78% | 32.59% |
| Linear | 20 / S2 | 0.3941 | 49.48% | 34.92% |
| Linear | 30 / S1 | 0.2440 | 128.15% | 103.58% |
| Linear | 30 / S2 | 0.2402 | 132.35% | 103.58% |
| Tree | 10 / S1 | 2.0298 | −0.00% | 0.00% |
| Tree | 10 / S2 | 1.8660 | −0.00% | 0.00% |
| Tree | 20 / S1 | 1.1245 | 8.50% | 6.07% |
| Tree | 20 / S2 | 1.0649 | 9.82% | 5.84% |
| Tree | 30 / S1 | 0.7210 | 29.14% | 23.40% |
| Tree | 30 / S2 | 0.7734 | 26.40% | 20.58% |
| Loop | 10 / S1 | 3.0133 | −0.00% | −0.00% |
| Loop | 10 / S2 | 2.8911 | 0.01% | −0.00% |
| Loop | 20 / S1 | 0.7104 | 23.27% | 15.76% |
| Loop | 20 / S2 | 0.6588 | 22.40% | 13.59% |
| Loop | 30 / S1 | 0.3969 | 69.28% | 56.92% |
| Loop | 30 / S2 | 0.4146 | 68.17% | 53.03% |

## Appendix C: Floorplan Blueprints

Structural diagrams (node positions and connectivity, not architectural drawings) for all floorplans are in `paper/figures/` — green circles are room-start nodes, orange squares are doors, **red diamonds are exits**, gray dots/lines are corridor and in-room navigation nodes and their connecting edges:

- Five benchmark floorplans: `figures/blueprint_FP01.png` through `blueprint_FP05.png`
- Nine unique synthetic layouts, **original (diagonal-affected) corpus**: `figures/blueprint_SYN_{linear,tree,loop}_{10,20,30}.png`
- Nine unique synthetic layouts, **[v4] diagonal-fixed V2 corpus**: `figures/blueprint_SYN_{linear,tree,loop}_{10,20,30}_V2.png`

**[v4] Before/after the diagonal-edge fix (Loop, 10 rooms):** in the original corpus, Loop's door-to-corridor and ring-to-exit connections cut diagonally straight to the door/exit node. In the V2 corpus, those same connections route through a right-angle elbow instead — visually confirming the fix described in Section 9.7, not just the numeric result.

| Original (diagonal) | V2 (fixed) |
|---|---|
| ![Loop 10 rooms, original](figures/blueprint_SYN_loop_10.png) | ![Loop 10 rooms, V2](figures/blueprint_SYN_loop_10_V2.png) |

Linear is visually identical between the two corpora (it never had diagonal edges); Tree shows the same right-angle correction as Loop, just at fewer points (one per branch rather than one per room).

Note that "Tree" refers to the zero-cycle graph property of the corridor subgraph — for a connected tree, edges = vertices − 1 and every edge is a bridge, an identity unrelated to the number of QUBO variables (e.g. Tree-10 has 20 QUBO variables but 37 bridges) — not a visually branching layout: the generator lays branches out as parallel corridor rows joined by a spine, which is graph-theoretically a tree but does not resemble a biological tree when drawn.

## Reproducibility

**[v4]** The diagonal-fixed synthetic corpus (18 floorplans, `*_V2` IDs) is at `data/floorplans/`, generated by the corrected `scripts/expansion/generate_synthetic_floorplan.py`. Its structural metrics are at `docs/expansion_synthetic_geometry_raw_V2.json`, CP-SAT reference energies at each floorplan's own `output/milp_gap/`, the Neal 10-repeat comparison (produced by `scripts/expansion/run_neal_repeats_v2_fixed.py`, which also fixes the pruned-vs-unpruned bug) at `docs/expansion_synthetic_neal_v2_fixed_raw.json`, and the Hybrid 10-repeat comparison (`scripts/expansion/run_hybrid_repeats_v2_fixed.py`) at `docs/expansion_synthetic_hybrid_v2_fixed_raw.json`. The combined 23-instance correlation dataset behind Table 9 is at `docs/expansion_v2_combined_23instance_raw.json`, and the Mann-Whitney significance results behind Section 9.7's solver-comparison recount are at `docs/expansion_v2_significance_raw.json`.

Source code, all 23 floorplan datasets (five benchmark, 18 synthetic), generated route catalogs, validation tests, CP-SAT/Neal/Hybrid benchmark outputs, blueprint figures, and this manuscript's source are available at `https://github.com/RomeroNatalia/evacuation-routes`, branch `main`, forked from and building on the original study's repository at `https://github.com/afishman2023/EvacCapstone`.
