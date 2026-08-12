# Expansion: Significance Testing and Per-Run Optimality Gaps

**Test:** Mann-Whitney U (independent two-sample, non-parametric).
Neal's randomness is local-seed-based; D-Wave Hybrid's is server-side
and unrelated -- the 30 runs of each are independent samples, not
paired observations, so Mann-Whitney U is the correct test (not a
paired test like Wilcoxon signed-rank).

**Bonferroni correction:** testing 5 floorplans from the same
underlying question ("is Hybrid better than Neal?") means alpha=0.05
should be corrected to alpha=0.01 (0.05/5) to control the family-wise
error rate.

## Results

| FP | Neal mean | Hybrid mean | U | p (two-sided) | p (Neal > Hybrid) | effect size r | sig. @ 0.01? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| FP01 | 0.704952 | 0.644706 | 854.0 | 2.44e-09 | 1.22e-09 | -0.898 | **yes** |
| FP02 | 0.643350 | 0.613582 | 749.0 | 1.02e-05 | 5.09e-06 | -0.664 | **yes** |
| FP03 | 0.605926 | 0.558868 | 827.0 | 2.60e-08 | 1.30e-08 | -0.838 | **yes** |
| FP04 | 1.502658 | 1.502658 | 0.0 | 1.69e-14 | 1.00e+00 | 1.000 | **yes** |
| FP05 | 0.793741 | 0.738094 | 826.0 | 2.83e-08 | 1.42e-08 | -0.836 | **yes** |

`p (Neal > Hybrid)` tests the paper's directional claim directly:
the one-sided alternative that Neal's energies are stochastically
greater (worse) than Hybrid's.

## Per-run optimality gap (all 30 runs, not just the best)

Against the certified MILP optimum from
`docs/EXPANSION_MILP_OPTIMALITY_GAPS.md`. This is a stricter test
than the paper's own "best observed energy" comparison -- it shows
the full spread of every run, including whether either solver ever
actually reaches the true optimum across 30 independent attempts.

| FP | MILP optimum | Neal gap % (mean / median / min / max) | Hybrid gap % (mean / median / min / max) | Hybrid ever exact? |
|---|---:|---|---|:---:|
| FP01 | 0.593857 | 18.71 / 19.04 / 7.24 / 25.56 | 8.56 / 9.28 / 1.08 / 13.19 | no |
| FP02 | 0.288830 | 122.74 / 123.06 / 102.69 / 142.06 | 112.44 / 113.57 / 99.16 / 126.19 | no |
| FP03 | 0.260012 | 133.04 / 134.43 / 109.65 / 147.30 | 114.94 / 114.93 / 91.27 / 129.57 | no |
| FP04 | 1.502658 | -0.00 / -0.00 / -0.00 / -0.00 | -0.00 / -0.00 / -0.00 / -0.00 | **yes** |
| FP05 | 0.615057 | 29.05 / 28.52 / 14.45 / 41.05 | 20.00 / 21.23 / 6.60 / 28.20 | no |

## Reading these results

**Caveat on p-values as practical significance**: a low p-value only
means the two distributions differ measurably -- it says nothing
about whether that difference is large enough to matter. FP04 is a
concrete example below: both solvers land within floating-point
noise (~1e-16) of the exact optimum on all 30 runs, yet Mann-Whitney
still reports p=1.69e-14, because even noise-level differences
become "significant" once they're perfectly consistent across 30
runs each. Practical significance always needs the gap-percent
columns above read alongside the p-value, not the p-value alone.

- **FP01**: statistically significant Hybrid advantage (p=2.44e-09, effect size r=-0.898). Neither solver ever reached the true optimum in 30 runs (closest: Neal 7.24%, Hybrid 1.08%).
- **FP02**: statistically significant Hybrid advantage (p=1.02e-05, effect size r=-0.664). Neither solver ever reached the true optimum in 30 runs (closest: Neal 102.69%, Hybrid 99.16%).
- **FP03**: statistically significant Hybrid advantage (p=2.60e-08, effect size r=-0.838). Neither solver ever reached the true optimum in 30 runs (closest: Neal 109.65%, Hybrid 91.27%).
- **FP04**: p=1.69e-14 is statistically significant but **not practically meaningful** -- both solvers reach the exact certified optimum on all 30 runs (gaps ~0% for both); the p-value reflects floating-point-noise-level differences, not a real quality gap.
- **FP05**: statistically significant Hybrid advantage (p=2.83e-08, effect size r=-0.836). Neither solver ever reached the true optimum in 30 runs (closest: Neal 14.45%, Hybrid 6.60%).
