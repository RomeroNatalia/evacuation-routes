# Assignment-Penalty Sweep Scripts

These are the current path-corrected sweep implementations.

- `sweep_assignment_penalty_neal.py`
- `sweep_assignment_penalty_hybrid.py`
- `sweep_assignment_penalty_qpu.py`

Each tests the automatic penalty and the manual values `2.5`, `3.0`, `4.0`, and `5.0`. The QPU version reuses its sampler stack, releases completed sample sets, writes a checkpoint after every cloud job, and resumes completed `(penalty, run)` pairs.
