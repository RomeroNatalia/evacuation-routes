# Canonical Logical QUBO

These files are one canonical copy of the logical QUBO shared by Neal, Leap Hybrid, and the direct QPU for the FP01 office dataset and automatic assignment penalty.

- `qubo_variable_index.csv`: variable-to-room/exit mapping
- `qubo_linear_coefficients.csv`: linear BQM biases
- `qubo_quadratic_coefficients.csv`: pairwise BQM interactions
- `qubo_upper_triangular.csv`: upper-triangular QUBO representation
- `qubo_dense_xtqx.csv`: dense matrix for literal `x^T Q x`

The copies previously repeated in every solver folder were intentionally consolidated here.
