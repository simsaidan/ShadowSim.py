"""Counterexample search: compare SDP (POVM) vs QCQP (projective) values."""

import sys
import numpy as np
from exclusion import sdp_exclusion, qcqp_unitary, random_pure_states, clustered_pure_states, random_mixed_states

GAP_TOL = 1e-5  # flag instances where projective - POVM exceeds this
HEAVY_RESTARTS = 60  # re-optimization budget for flagged instances


def one_trial(rhos, rng, restarts=8):
    sdp = sdp_exclusion(rhos)
    proj, _ = qcqp_unitary(rhos, rng, restarts=restarts)
    return sdp, max(proj, 0.0)


def run_batch(name, sampler, trials, rng, restarts=8):
    max_gap, max_gap_instance = -np.inf, None
    flagged = []
    for t in range(trials):
        rhos = sampler(rng)
        sdp, proj = one_trial(rhos, rng, restarts=restarts)
        gap = proj - sdp
        if gap > max_gap:
            max_gap, max_gap_instance = gap, rhos
        if gap > GAP_TOL:
            # candidate: retry projective side much harder, and re-solve the
            # SDP with a second solver, before believing it
            proj2, _ = qcqp_unitary(rhos, rng, restarts=HEAVY_RESTARTS)
            sdp2 = sdp_exclusion(rhos, solver="SCS")
            gap2 = proj2 - max(sdp, sdp2)
            print(
                f"  [{name} trial {t}] candidate gap {gap:.3e} -> "
                f"after {HEAVY_RESTARTS} restarts + SDP recheck: {gap2:.3e}",
                flush=True,
            )
            if gap2 > GAP_TOL:
                flagged.append((gap2, rhos))
    print(f"[{name}] trials={trials}  max gap={max_gap:.3e}  surviving candidates={len(flagged)}", flush=True)
    return flagged, max_gap, max_gap_instance


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rng = np.random.default_rng(seed)
    all_flagged = []

    for d in (4, 5, 6):
        n = d
        batches = [
            (f"d={d} haar pure", lambda r, n=n, d=d: random_pure_states(n, d, r), 30),
            (f"d={d} clustered s=0.10", lambda r, n=n, d=d: clustered_pure_states(n, d, r, 0.10), 60),
            (f"d={d} clustered s=0.15", lambda r, n=n, d=d: clustered_pure_states(n, d, r, 0.15), 60),
            (f"d={d} clustered s=0.20", lambda r, n=n, d=d: clustered_pure_states(n, d, r, 0.20), 60),
            (f"d={d} clustered s=0.30", lambda r, n=n, d=d: clustered_pure_states(n, d, r, 0.30), 60),
            (f"d={d} mixed rank2", lambda r, n=n, d=d: random_mixed_states(n, d, r, 2), 30),
        ]
        for name, sampler, trials in batches:
            flagged, _, _ = run_batch(name, sampler, trials, rng)
            all_flagged.extend(flagged)

    print()
    if all_flagged:
        print(f"*** {len(all_flagged)} surviving candidate counterexample(s) ***")
        gap, rhos = max(all_flagged, key=lambda x: x[0])
        np.save("candidate_states.npy", np.array(rhos))
        print(f"largest surviving gap: {gap:.6e}  (states saved to candidate_states.npy)")
    else:
        print("No counterexample found: projective optimum matched the POVM SDP value (within 1e-5) on every instance.")


if __name__ == "__main__":
    main()
