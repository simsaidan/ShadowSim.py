# POVM vs projective measurements for state exclusion — counterexample search

Standalone experiment (unrelated to the rest of this repo).

## Problem

Compare the optimal state-exclusion value over POVMs (an SDP) against the value
over projective measurements (a QCQP, rank-1 projectors / orthonormal basis).
Projective measurements are a subset of POVMs, so QCQP >= SDP always; a
counterexample to equivalence is an instance with a strict gap. Known equal for
d=2 and for 3 pure states in d=3 (Molina, arXiv:1702.06449); open for d>3
*for pure states with n <= d*.

## Files

- `exclusion.py` — SDP (cvxpy/Clarabel, cross-checked with SCS), the original
  SLSQP QCQP, and a smoother unconstrained QCQP over unitaries (U = expm(iH)).
- `search.py` — random search over Haar pure, clustered (high-overlap) pure,
  and random rank-2 mixed ensembles for d = 4, 5, 6 (n = d).
- `analyze_candidate.py` — compares rank-1 projective vs *general* projective
  (projectors of any rank pattern) on flagged instances.
- `mixed_counterexample.npy` — 4 rank-2 mixed states in d=4 with a robust
  value gap: POVM 0.00701 vs best projective (all rank patterns) 0.02307.
- `perfect_exclusion_witness.npy` — 5 rank-2 mixed states in d=5 that are
  *certified* perfectly POVM-antidistinguishable (kernel-restricted SDP
  feasible, Tr(rho_i M_i) ~ 1e-17) but for which extensive local search over
  all projective rank patterns never got below ~8.6e-4.

## Results

1. **Pure states (the actual open problem): no counterexample.** Across
   ~750 instances (Haar and high-overlap ensembles, d = 4, 5, 6, including
   many with strictly positive exclusion value and many near the
   antidistinguishability boundary), the projective optimum matched the POVM
   SDP value to within 1e-8 on every instance.

2. **Mixed states: robust gaps exist**, both for the rank-1 QCQP as written
   (gaps up to ~0.03) and even for general projective measurements. This does
   not resolve the open problem (which is about pure states) — for mixed
   states a POVM advantage is expected. Heuristic: a rank-1 projective
   perfect exclusion needs n vectors, one inside each ker(rho_i), forming an
   orthonormal basis; for rank-2 states in d=5 the kernels are 3-dimensional,
   giving 30 real parameters against 25 orthonormality constraints, so
   generically infeasible, while the POVM feasibility problem has 45 free
   parameters and is generically feasible.

## Caveats

Projective values come from local optimization (many restarts, two
parametrizations, all rank patterns enumerated), so they are upper bounds;
"no gap" conclusions are rigorous (upper bound met the SDP lower bound), but
the positive mixed-state gaps are not globally certified.
