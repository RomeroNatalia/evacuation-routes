# Review — 9.22.26

**Manuscript reviewed:** `paper/arxiv_whitepaper.md`
**Commit at time of review:** `ef302ca` (2026-08-21)
**Reviewer framing:** External review received by the authors, written from the perspective of a quantum-computing referee in the style of D-Wave's applied-annealing research community. Reproduced here verbatim as the review-of-record this revision cycle responds to. See `plan_9.22.26.md` for the derived action plan.

---

Yes. **There is a publishable paper here.** But in its present form I would expect a strong quantum-computing referee to request **major revision**, primarily because the paper makes a stronger causal/structural claim than the current experimental design supports.

Reading this as I would expect someone in Andrew King's orbit to read it: the interesting result is **not that D-Wave Hybrid beats Neal**. The interesting result is that once you introduce a strong classical reference, **both annealing approaches can be dramatically far from the reference on particular structured instances**, and you then try to identify what structural property predicts that failure. That is potentially a good paper.

### My referee-style assessment

| Area                        | Assessment                                    |
| --------------------------- | --------------------------------------------- |
| Scientific question         | **Strong**                                    |
| QUBO formulation            | **Reasonable / publishable**                  |
| Classical reference         | **Major improvement**                         |
| Quantum experiment          | **Useful but limited**                        |
| Statistical analysis        | **Good direction, needs tightening**          |
| Structural result           | **Interesting, currently overclaimed**        |
| Quantum advantage claim     | **Correctly avoided**                         |
| Reproducibility             | **Strong**                                    |
| Novelty                     | **Moderate–strong if repositioned correctly** |
| Publishable now?            | **Not quite**                                 |
| Publishable after revision? | **Yes**                                       |

## 1. The strongest part of the paper

This is the part I would preserve and build the entire paper around.

You discovered that the apparently respectable Neal/Hybrid solutions are actually terrible on FP02 and FP03 once compared with CP-SAT:

* FP02: Hybrid **120.82%** above reference.
* FP03: Hybrid **94.31%** above reference.
* Neal is even worse.
* Yet the relative Hybrid-vs-Neal comparison would not reveal the problem.

That is scientifically meaningful.

Even better is FP03. Your CP-SAT assignment has approximately:

> distance = 254.25, congestion = 11.85

while Hybrid/Neal produce roughly:

> distance = 551–595, congestion = 134–148.

So the annealing solutions are not simply trading distance for congestion. They are **dominated on both objectives** by a much better assignment.

That result would make me keep reading.

It changes the paper from:

> "We applied quantum annealing to evacuation."

which is not particularly novel anymore,

into:

> **"Why do annealing-based QUBO solvers fail badly on some apparently ordinary routing instances, and can graph structure predict that failure?"**

That is much more interesting.

---

## 2. The biggest problem: you have not established that corridor diameter is *the mechanism*

This is where I would attack the manuscript as a referee.

You write:

> "**Corridor diameter is the strongest univariate predictor for both solvers**"

with r=0.868 Neal and r=0.853 Hybrid.

That's a strong correlation.

You also show that adding diameter to variable count raises R² from 0.682 to 0.857 for Neal, and 0.700 to 0.850 for Hybrid.

Very good.

But then the manuscript goes farther and effectively says: long corridor ⇒ more route interactions ⇒ harder QUBO.

That has **not yet been demonstrated**.

You yourself identify the issue correctly in the limitations:

> "Corridor diameter and mean route-hop length are correlated with each other and not yet fully statistically separated."

That's not a small limitation. **It goes directly to your principal conclusion.**

### What I would require

Construct synthetic instances in which you independently manipulate: number of variables (N), corridor diameter, average route length, number of exits, route overlap, QUBO interaction density, coefficient distribution / dynamic range.

Ideally create matched families such as N = constant, D = {5, 10, 20, 40, ...} while keeping other important quantities approximately constant.

Then ask: optimality gap = f(D) under controlled conditions.

If the gap increases monotonically with D, **then you have a much stronger paper.**

---

## 3. A quantum referee will immediately ask: where is the QUBO-graph analysis?

This is probably the biggest missing *physics/quantum annealing* analysis.

You're analyzing the **physical navigation graph**. But the annealer doesn't see the navigation graph. It sees H(x) = Σ h_i x_i + Σ J_ij x_i x_j.

Therefore I want to know what corridor diameter does to the **logical interaction graph and energy landscape**: logical QUBO degree, mean/max degree, interaction density, number of nonzero J_ij, J-coefficient distribution, coefficient dynamic range, weighted degree, graph treewidth or proxies, spectral properties, frustration-related metrics, degeneracy, number/density of low-energy states, energy gaps between best competing configurations, embedding size, chain lengths, chain-break fraction.

Right now Section 10.3 provides a plausible explanation (longer routes touch more edges, producing more opportunities for interactions with other routes). Yes. But **show it quantitatively.**

You may discover that corridor diameter itself isn't the fundamental quantity. Perhaps: D_corridor → route overlap → |J| density → rugged landscape → annealing failure. If so, **QUBO interaction structure**, rather than architectural corridor diameter, is the real physical/computational mechanism. That would be a better result.

---

## 4. There is an extremely interesting observation you aren't exploiting enough

FP02 and FP03 could not be embedded on the QPU — and those happen to be the two problems where annealing solutions have enormous optimality gaps. The manuscript already suggests embedding difficulty and optimization difficulty may share a common structural origin. **This could become one of the paper's most interesting results.** But right now n=5 real layouts is nowhere near enough to support it.

Test embedding systematically on the synthetic corpus. For each instance obtain: N_logical, E_logical, density, N_physical, mean chain length, max chain length, embedding success probability, chain-break rate, optimality gap. Then determine whether classical-SA difficulty ↔ Hybrid difficulty ↔ minor-embedding difficulty correlate after controlling for N. If so, that's much more interesting than "corridor diameter predicts difficulty."

---

## 5. CP-SAT is simultaneously a strength and a vulnerability

This section is scientifically responsible — you explicitly acknowledge CP-SAT certifies the *integer-scaled* formulation, not necessarily the original float objective. Good.

A referee will nevertheless ask: how do I know your 120% gap isn't partially an artifact of scaling/rounding?

### I would consider this required before submission

Do at least one of: (1) solve using several scaling factors (S = 10³, 10⁴, 10⁵, 10⁶); (2) demonstrate that the selected assignment stabilizes; (3) derive a bound proving rounding cannot alter the optimum; (4) use an exact/rational or sufficiently high-precision alternative solver; (5) enumerate a subset of intermediate instances and verify exact agreement.

You already validate FP04 against exhaustive enumeration to ten decimal places — excellent. Extend that validation. If the CP-SAT assignment remains identical across increasingly precise scalings, this reviewer concern becomes much smaller.

---

## 6. The statistical unit is problematic

Your own limitations note: the 18 synthetic instances correspond to **9 distinct graph configurations**, each evaluated under two occupancy/capacity draws. So treating all 18 as fully independent structural observations inflates the effective structural sample size.

You should probably use a hierarchical/mixed model: gap_ij = β₀ + β₁D_i + β₂N_i + u_i + ε_ij, where i identifies topology/size graph and j identifies occupancy/capacity realization.

Or generate substantially more independent graph realizations. I strongly prefer the second option: not "3 topologies × 3 sizes × 2 parameter seeds" but something closer to "3–5 topology classes × 5–8 sizes × 10–20 graph realizations" — perhaps 150–500 instances. CP-SAT is taking <2s each, so classical generation is not prohibitive. You don't necessarily need Hybrid runs on all of them — run Neal on the entire corpus and Hybrid/QPU on a stratified subset.

---

## 7. I would remove or soften one claim

"statistically confirming that corridor diameter ... is the strongest predictor of solver difficulty" is too strong.

Your data support: "corridor diameter is the strongest predictor **among the structural metrics evaluated**." Those are not equivalent statements. There could easily be a better predictor you didn't measure — especially something directly defined on the QUBO interaction graph. The abstract currently makes the stronger claim. I would change that before peer review.

---

## 8. Your QPU experiment needs stronger treatment

Useful results exist (FP04 exact optimum, FP01/FP05 low valid-sample rates, FP02/FP03 cannot embed), but from a quantum-computing perspective the direct-QPU portion currently feels appended rather than central. A serious quantum paper should provide more detail on embedding → chains → chain breaks → solution quality, plus gauge statistics, chain-strength sensitivity, anneal-time sensitivity, embedding variability, and perhaps anneal offsets/reverse annealing only if scientifically motivated. I would **not** add exotic D-Wave controls merely to make the paper appear more quantum — the useful question is whether the hardware behavior illuminates the structural phenomenon.

---

## 9. One thing you did exactly right

Do **not** add a quantum-advantage claim. The manuscript explicitly avoids this and repeats the limitation. Keep that — CP-SAT solving every instance in under two seconds makes a quantum-advantage framing indefensible here, but that doesn't hurt the paper. The scientific story is instead: understanding structural failure modes of annealing-based optimization through an exactly benchmarked routing-QUBO family. That's credible.

---

## 10. What I would do before submission

If this were my student, I would not spend the next month improving the evacuation model. I would run three focused experiments:

| Priority               | Experiment                                                  | Why                                                     |
| ----------------------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| **1 — essential**      | Independent sweep of corridor diameter vs route length/size | Establishes whether your main structural claim survives |
| **2 — essential**      | Analyze logical QUBO interaction graph vs optimality gap    | Provides mechanism relevant to quantum optimization     |
| **3 — very important** | CP-SAT scaling/rational validation                          | Protects the entire optimality-gap result                 |

Then, if resources permit: synthetic corpus expansion + embedding analysis.

---

## My publication verdict

**Current manuscript:** Major revision — potentially publishable. I would not reject it because there is a legitimate result and the authors are unusually transparent about negative results and limitations.

**With the three experiments above:** I would consider it a solid quantum optimization / applied quantum annealing paper.

**With those experiments + systematic embedding/QUBO-landscape analysis:** it could become considerably more interesting: Graph structure → QUBO interaction structure → energy-landscape difficulty → classical/Hybrid/QPU behavior. That is the paper I think you actually have hiding inside this draft. The evacuation problem then becomes the **controlled physical testbed**, rather than the primary contribution. That repositioning is important.

And one final point: the manuscript's strongest scientific characteristic is that it **falsifies its own initial hypothesis**. You started with bridge count, built controlled instances, discovered it did not explain the behavior, and found a substantially better predictor. That's exactly the kind of methodological story worth preserving.

**My score as a hypothetical referee today: 6–7/10, major revision. With the QUBO-structure and controlled-diameter experiments done correctly: ~8/10 and I would lean accept.**

---

### Addendum: cross-reference to the companion review of the same draft

A second, independently-produced review of the same commit (`ef302ca`), written from a similar D-Wave/quantum-annealing-researcher persona, converged on several of the same points (chain-break reporting, embedding heuristic/hardware-generation choice, penalty-scaling ablation) and added two points not raised above: (1) chain-break fraction and chain-strength sensitivity are never reported for the successful FP01/FP04/FP05 QPU runs, which this review's §3–4 also implies but does not state as directly; (2) the paper's title/abstract foreground "quantum annealing" more than the thin, mostly-negative QPU results (§9.7) support — worth softening framing rather than only adding instrumentation. See `plan_9.22.26.md` item 6.
