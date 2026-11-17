"""Analyze the flagged mixed-state instances.

The QCQP forces each outcome to be a rank-1 projector (one basis vector per
state). A *general* projective measurement lets outcome i be a projector of
any rank (including 0), as long as they are mutually orthogonal and sum to I.

For a fixed orthonormal basis U, the best general projective measurement
assigns each basis vector u_c to the outcome i minimizing <u_c|rho_i|u_c>,
so   general-projective value = min_U  sum_c min_i <u_c| rho_i |u_c>.
We optimize this over U with the same expm(iH) parametrization.
"""

import numpy as np
from scipy.optimize import minimize
from scipy.linalg import expm
from exclusion import sdp_exclusion, qcqp_unitary


def general_projective(rhos, rng, restarts=40):
    n = len(rhos)
    d = rhos[0].shape[0]
    iu = np.triu_indices(d, 1)
    m = d * (d - 1) // 2

    def params_to_U(x):
        H = np.zeros((d, d), dtype=complex)
        H[np.diag_indices(d)] = x[:d]
        H[iu] = x[d : d + m] + 1j * x[d + m :]
        H = H + H.conj().T - np.diag(np.diag(H).real)
        return expm(1j * H)

    def f(x):
        U = params_to_U(x)
        # cost[c, i] = <u_c| rho_i |u_c>; assign each column to its best state
        cost = np.array([[(U[:, c].conj() @ rhos[i] @ U[:, c]).real for i in range(n)] for c in range(d)])
        return cost.min(axis=1).sum()

    best = np.inf
    for _ in range(restarts):
        x0 = rng.standard_normal(d * d) * 1.5
        res = minimize(f, x0, method="Nelder-Mead", options={"maxiter": 20000, "fatol": 1e-12, "xatol": 1e-10})
        best = min(best, res.fun)
    return best


def main():
    rng = np.random.default_rng(123)
    rhos = list(np.load("candidate_states.npy"))
    n, d = len(rhos), rhos[0].shape[0]
    print(f"candidate: n={n}, d={d}, ranks={[np.linalg.matrix_rank(r, tol=1e-9) for r in rhos]}")

    sdp = sdp_exclusion(rhos)
    r1, _ = qcqp_unitary(rhos, rng, restarts=200)
    gen = general_projective(rhos, rng, restarts=40)
    print(f"SDP (POVM)                 : {sdp:.10f}")
    print(f"QCQP rank-1 projective     : {r1:.10f}   (200 restarts)")
    print(f"general projective         : {gen:.10f}   (40 restarts)")
    print(f"rank-1 gap  = {r1 - sdp:.3e}")
    print(f"general gap = {gen - sdp:.3e}")


if __name__ == "__main__":
    main()
