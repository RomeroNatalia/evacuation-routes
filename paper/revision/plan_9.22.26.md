# Plan — 9.22.26

Response plan for `review_9.22.26.md`. Items are numbered against that review's own priority framing (§10's table plus §7's quick-fix and the addendum's cross-referenced points). When every non-optional item below is checked off, produce `paper/revision/version_9.22.26.tex` as the finished revision — a full paper draft in the same format as `revision1.tex`, incorporating all completed items.

**Target manuscript:** `paper/arxiv_whitepaper.md` (currently mirrors `paper/main_v4.tex`); commit `ef302ca` was the version reviewed.

---

## 1. CP-SAT integer-scaling stability check
**Review ref:** §5 / §10 priority 3 ("very important") — protects the entire optimality-gap result.
**Status: DONE (9.22.26).**

- Script: `scripts/expansion/scaling_stability_check.py`
- Data: `docs/expansion_cpsat_scaling_stability_raw.json`
- Result: for all 5 benchmark floorplans plus the worst-case synthetic instance (SYN_LIN_30, ~130% gap), the CP-SAT-selected assignment and recomputed float64 energy are byte-identical across `LOAD_SCALE` = 10 → 100,000 (4 orders of magnitude spanning the paper's reported setting of 1,000). Recomputed energies also match Table 3 exactly, as an internal consistency check.
- **Remaining sub-task: DONE (9.22.26).** Added a new §6.5 "Scaling-stability check" to both `paper/main_v4.tex` and `paper/arxiv_whitepaper.md`, updated the §6.3 hedge sentence and the corresponding Limitations bullet to reference it, updated the Future Work order-preservation-proof item to note the empirical check is already done, and added the script/data to Reproducibility.

**Item 1 fully closed.**

## 2. Soften the overclaimed predictor/causal language
**Review ref:** §7 (quick fix) and §2 (biggest problem — causal claim not yet demonstrated).
**Status: DONE (9.22.26).**

- [x] Abstract, contributions bullets, §9.6.1 heading/text, and Conclusion in both `paper/arxiv_whitepaper.md` and `paper/main_v4.tex`: "the single strongest predictor of solver difficulty" → "the strongest predictor among the structural metrics evaluated," everywhere this claim appeared (also fixed a pre-existing internal inconsistency in `main_v4.tex`'s contributions list, which still reported the pre-diagonal-fix numbers).
- [x] §9.6.1 now explicitly flags that the correlation alone doesn't establish causality, and points to item 3's sweep (deconfounds diameter from N) and item 4 (still open — deconfounds diameter from the logical QUBO graph) as the two things that would.
- [x] New §9.6.3 / `sec:dsweep` added to both files reporting item 3's sweep result directly in the body, not just as a caveat.
- [ ] §10.3 ("Why corridor length, mechanistically") not yet reframed — still worth a pass once item 4 either confirms or complicates the mechanism story, but no longer blocking since the N-confound (the sharper of the two objections) is now closed.

## 3. Independent sweep: corridor diameter vs. route length/size
**Review ref:** §2 and §10 priority 1 ("essential") — the review's single highest-priority item; the paper's current diameter-vs-route-length confound is a self-acknowledged limitation.
**Status: DONE (9.22.26), all three solvers.**

- [x] Extended `scripts/expansion/generate_synthetic_floorplan.py`'s `build_linear` with an optional `--corridor-length` argument, decoupled from `--rooms`: rooms attach round-robin (`r % corridor_len`), so corridor length (and diameter) can vary independently of room count / variable count N. Default behavior (argument omitted) verified byte-identical to the published corpus (diffed against `SYN_LIN_20_S1_V2`).
- [x] Generated a 12-instance sweep: rooms=20, exits=4 fixed (**N=80 variables, identical for all 12 instances**), corridor_length ∈ {6, 10, 14, 20, 30, 42} × 2 seeds. IDs: `SYN_DSWEEP_L{length:02d}_S{seed}`.
- [x] Solved CP-SAT reference (`scripts/expansion/milp_optimality_gap.py`) and 10-repeat Neal (`scripts/expansion/diameter_sweep_neal.py`, reusing the published corpus's exact methodology — same REPEATS/READS/SWEEPS/N_SEEDS and corrected unpruned-energy recomputation) for all 12. Structural metrics via `scripts/expansion/diameter_sweep_geometry.py` (reuses `geometry_bottleneck_analysis.analyze_floorplan`).
- [x] **Result: gap increases with corridor diameter at fixed N=80, and the relationship is strong and monotonic (apart from minor noise around D=19–29).** Neal gap rises from ~20% (D=5) to ~65% (D=41). Pearson r(diameter, gap) = **0.943** (p=4.4×10⁻⁶); Spearman ρ = 0.975 (p=6.9×10⁻⁸), n=12. This directly answers the review's §2 requirement ("N=constant, D={5,10,20,40,...}, ask whether gap=f(D) increases monotonically") — it does.
- Data: `docs/expansion_diameter_sweep_geometry_raw.json`, `docs/expansion_diameter_sweep_neal_raw.json`, and each instance's own `data/floorplans/SYN_DSWEEP_*/output/milp_gap/`.
- Note: within this design, corridor diameter and mean route-hop length remain collinear by construction (a longer single-spine corridor mechanically produces longer routes) — this experiment deconfounds diameter from **N**, which is what the review's §2 asked for, but does not separately deconfound diameter from route length (that pairing is a distinct, already-documented limitation in §11/Limitations).
- [x] **Hybrid run (user directed 9.22.26).** 120 Hybrid calls (12 instances × 10 repeats) completed via `scripts/expansion/diameter_sweep_hybrid.py`. Result: Pearson r(diameter, gap) = **0.930** (p=1.2×10⁻⁵), Spearman ρ = 0.961 (p=6.5×10⁻⁷) — replicates Neal's finding under Hybrid as well. Hybrid's gap is lower than Neal's in all 12/12 instances of this sweep (n too small to treat that ratio as its own finding, but directionally consistent with the broader corpus's 17/23). Data: `docs/expansion_diameter_sweep_hybrid_raw.json`.
- [x] Both papers' §9.6.3/`sec:dsweep`, abstract, and conclusion updated with the combined Neal+Hybrid table and stats.

**Item 3 fully closed — all three solvers (CP-SAT, Neal, Hybrid) now support the diameter effect at fixed N.**

## 4. Logical QUBO-interaction-graph metrics
**Review ref:** §3 and §10 priority 2 ("essential") — the review's core complaint that the paper analyzes the navigation graph, not the graph the solver actually searches.
**Status: DONE (9.22.26) — scoped down from the review's full list.**

- [x] Computed, for all 23 published instances, directly on the same BQM `solve_qubo_neal.py`/the paper's benchmarks build (via `neal_budget_scaling_test.py`'s `load_and_build_bqm`, reused as-is): logical variable degree (mean/max), interaction density, count of nonzero J_ij, and coefficient dynamic range. Two variants: "full" (penalized BQM as solvers see it) and "congestion-only" (isolates the corridor-driven coupling from the assignment-penalty structure, which is fixed by room/exit counts). Script: `scripts/expansion/qubo_graph_metrics.py`; data: `docs/expansion_qubo_graph_metrics_raw.json`.
- [x] Added as new Table 6b / `tab:qubograph` in both papers (Section 9.6.4 / `sec:qubograph`), with both univariate and partial (controlling for N) correlations against 10-repeat mean gap.
- [x] **Result (honest negative finding, reported as such):** univariate, these QUBO-graph metrics correlate about as strongly as corridor diameter (r≈0.75–0.83) — but that's mostly a size effect. Once N is partialed out, degree and density collapse to ~0 (Neal r=−0.136, Hybrid r=−0.280 for degree), while corridor diameter retains r=0.742 Neal / 0.707 Hybrid. First-order QUBO-graph statistics do not out-predict corridor diameter; if anything they're largely a proxy for N. This doesn't strengthen the mechanism story mechanistically, but it does close the specific concern that a trivial logical-graph statistic would have explained the gap better than the physical corridor structure already does.
- **Explicitly deferred, not required for this revision:** treewidth/spectral properties, frustration metrics, degeneracy, and low-energy-state density — the review's full list is closer to a second paper's worth of analysis; flagged as future work rather than a blocker for `version_9.22.26`.

## 5. Statistical unit correction (9 structures × 2 seeds ≠ n=23)
**Review ref:** §6 — inflated effective sample size in the structural correlation/regression.
**Status: DONE (9.22.26) — scoped down from the review's 150–500 instance suggestion.**

- [x] Applied a mixed-effects model (`statsmodels` `MixedLM`, installed for this analysis — not previously a project dependency) with a random intercept per unique graph structure: gap_ij = β₀ + β₁·diameter_i + β₂·n_variables_i + u_i + ε_ij, 14 groups (5 unique benchmark floorplans + 9 unique synthetic topology/size structures) across the 23 observations. Script: `scripts/expansion/mixed_effects_diameter_check.py`; data: `docs/expansion_mixed_effects_raw.json`.
- [x] **Result: diameter remains significant after proper clustering, for both solvers.** Neal: diameter coefficient 2.38 (p=0.002); Hybrid: 1.84 (p=0.006); both alongside a significant n_variables term. Likelihood-ratio test (diameter added vs. n_variables-only model): Neal LR=7.25 (p=0.007), Hybrid LR=5.94 (p=0.015). This formalizes what the paper's existing informal "14 unique instances" footnote already suggested, using all 23 seed-level observations rather than discarding half of them.
- Did not pursue the 150–500 instance corpus expansion — the mixed-effects model directly answers the "is n=23 inflating significance" question without needing more data, which is the more targeted fix for what the review's §6 was actually worried about.

## 6. QPU instrumentation and title/abstract framing (stretch goal)
**Review ref:** §4, §8, and the addendum (cross-referenced from the companion review's chain-break and embedding-heuristic points, plus its framing objection: title/abstract foreground "quantum annealing" more than the thin, mostly-negative §9.7 QPU results support).
**Status: OPTIONAL — not required for `version_9.22.26`.**

- [ ] If pursued: report chain-break fraction and chain-strength sensitivity for the three embeddable floorplans (FP01/FP04/FP05); check whether an alternative embedding heuristic changes the FP02/FP03 embedding-failure outcome.
- [ ] Independent of instrumentation: consider softening the abstract/title's emphasis on "quantum annealing" to match what §9.7 actually shows, regardless of whether item 6's instrumentation work happens.
- Deprioritized because it requires D-Wave Leap/QPU quota and does not gate the paper's now-primary claim (structural predictors of classical/Hybrid difficulty against the CP-SAT reference).

## 7. Out of scope
**Review ref:** §8 — the review explicitly recommends against this.

- Reverse annealing, anneal-time sweeps, pause/quench exploration, anneal offsets: not pursued. The review's own guidance is not to "add exotic D-Wave controls merely to make the paper appear more quantum" — the QPU arm's role in this paper is illustrative, not central.

---

## Completion criteria for `version_9.22.26`

Produce `paper/revision/version_9.22.26.tex` once items **1–5** are checked off. Item 6 is optional and does not block version_9.22.26 — if left undone, its status should be carried forward explicitly in that version's Limitations section rather than silently dropped. Item 7 stays out of scope permanently for this revision cycle.

**Status: DONE (9.22.26).** Items 1–5 are all complete. `paper/revision/version_9.22.26.tex` has been written — a clean, consolidated LaTeX draft (not a revision-tracking document like `main_v4.tex`), built from the finalized `arxiv_whitepaper.md` content and `revision1.tex`'s LaTeX skeleton/bibliography. It uses the V2 (diagonal-fixed) corpus numbers throughout as the primary numbers (no old-vs-new layering), includes all four new subsections (6.5 scaling-stability, 9.6.3 deconfounding sweep, 9.6.4 QUBO-graph metrics, 9.6.5 mixed-effects check), and carries item 6 forward explicitly in its Limitations and Future Work sections as not yet done. Structural sanity-checked (balanced environments, all `\ref`/`\label` and `\cite`/`\bibitem` pairs matched) but not compiled with `pdflatex`, which is not installed in this environment — recommend a compile pass before submission. `paper/main_v4.tex` and `paper/arxiv_whitepaper.md` remain the living/revision-tracking and standalone-markdown copies respectively, both already updated with the same content in parallel.
