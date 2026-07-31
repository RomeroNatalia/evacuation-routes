# Current Mathematical Model

## Plain-language description

Each room must choose one stored route to one exit. Shorter routes are preferred. If selected routes share hallways, doors, or exit connections, their occupants add to the same physical-edge load and create a squared congestion cost. A penalty makes selecting zero routes or multiple routes for one room expensive.

## Sets and parameters

- `R`: rooms
- `E`: exits
- `K`: physical graph edges
- `I_r`: stored candidate routes for room `r`
- `d_i`: physical Dijkstra distance of route `i`
- `p_r`: occupancy of room `r`
- `a_ik`: 1 if route `i` uses edge `k`, otherwise 0
- `c_k`: edge capacity units
- `C_k = 10 c_k`: current effective edge capacity in people

## Binary decision variable

For each stored room-to-exit route:

\[
x_i =
\begin{cases}
1, & \text{route } i \text{ is selected},\\
0, & \text{otherwise.}
\end{cases}
\]

## Edge utilization

The normalized load placed on edge `k` by route `i` is

\[
n_{ik}=\frac{p_{r(i)}a_{ik}}{C_k}.
\]

The selected utilization of edge `k` is

\[
u_k(x)=\sum_i n_{ik}x_i.
\]

## Normalization scales

The distance scale is

\[
S_D=\max\left(1,\sum_r\max_{i\in I_r}d_i\right).
\]

For each edge, the code forms a maximum feasible normalized load under one selected route per room:

\[
m_k=\sum_r\max_{i\in I_r}n_{ik}.
\]

The congestion scale is

\[
S_C=\max\left(1,\sum_k m_k^2\right).
\]

## Complete logical QUBO

\[
H(x)=
\frac{1}{S_D}\sum_i d_i x_i
+
\frac{5}{S_C}\sum_k\left(\sum_i n_{ik}x_i\right)^2
+
A\sum_r\left(1-\sum_{i\in I_r}x_i\right)^2.
\]

The three terms are normalized distance, normalized squared congestion, and the exactly-one assignment penalty.

## Assignment-penalty expansion

For one room:

\[
A\left(1-\sum_i x_i\right)^2
=
A-A\sum_i x_i+2A\sum_{i<j}x_ix_j,
\]

because binary variables satisfy `x_i^2 = x_i`. The penalty is zero only when exactly one route is selected.

## Automatic penalty

For each route `i`, the code starts with its base linear cost and then adds the largest positive interaction it could have with one selected route from every other room. Let the largest resulting feasible marginal be `M_max`. The automatic value is

\[
A=1.5\left(M_{\max}+0.25\right).
\]

For the saved FP01 office dataset:

\[
A\approx1.889696.
\]

This value is recalculated when the floorplan, occupancy, candidate routes, or capacities change.

## Interaction pruning

Congestion-only pairwise coefficients with absolute magnitude below `10^-4` are removed before the exactly-one interactions are added. Exactly-one interactions are never pruned.

## Report-only overload metric

The solver also reports

\[
5\sum_k\max(0,u_k-1)^2,
\]

but this overload-only quantity is not part of the optimized QUBO and is not a hard capacity constraint.
