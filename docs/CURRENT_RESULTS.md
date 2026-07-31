# FP01 Saved Results

These are the completed original-office experiments used in the prior discussion. FP02–FP05 were added later and do not yet include cloud solver results.

# Current Saved Results

All normalized energies below belong to the current normalized formulation and should not be compared numerically with the older pre-normalization energies.

## Ten-run benchmark

| Solver | Best energy | Mean energy | Energy standard deviation | Best distance | Mean distance | Mean valid-sample rate |
|---|---:|---:|---:|---:|---:|---:|
| Leap Hybrid | 0.625564 | 0.650853 | 0.015053 | 108.00 | 112.275 | 100% |
| Neal simulated annealing | 0.678656 | 0.710071 | 0.017604 | 119.50 | 122.075 | 100% |
| Direct QPU | 0.777351 | 0.914233 | 0.085753 | 131.75 | 150.200 | 1.09% |

Every solver found a valid best assignment in all ten jobs. Hybrid produced the best observed solution quality and the most consistent energies. Neal remained competitive and always generated valid samples. The direct QPU found valid best assignments, but valid states represented only about 1% of its returned samples.

## Best saved assignments

| Solver | Distance | Raw congestion | Overloaded edges | Maximum utilization |
|---|---:|---:|---:|---:|
| Leap Hybrid | 108.00 | 174.162847 | 11 | 140% |
| Neal simulated annealing | 119.50 | 180.570486 | 12 | 155% |
| Direct QPU | 131.75 | 225.273264 | 18 | 220% |

## Assignment-penalty sweep

The automatic value `A ≈ 1.889696` was compared with `2.5`, `3.0`, `4.0`, and `5.0`, using five independent runs per setting and solver.

- Neal returned 100% valid samples at every tested penalty. Increasing the penalty did not improve average solution quality.
- Hybrid returned valid assignments at every penalty and had its best average and best individual result at the automatic value.
- The direct QPU's mean valid-sample rates were approximately `1.38%`, `1.20%`, `1.02%`, `0.92%`, and `1.16%` as the penalty increased. A larger penalty did not solve the low-feasibility problem.

The current conclusion is to retain the automatic penalty and investigate QPU embedding/chain behavior separately rather than increasing `A` further.
