"""POVM vs projective measurements for quantum state exclusion.

SDP  : min sum_i Tr(rho_i M_i)  s.t. M_i >= 0, sum_i M_i = I      (POVMs)
QCQP : min sum_i <v_i| rho_i |v_i>  s.t. {v_i} orthonormal        (rank-1 projective, n = d)

Projective measurements are a subset of POVMs, so QCQP >= SDP always.
A counterexample to their equivalence is an instance where the *global*
QCQP optimum is strictly above the SDP optimum.
"""

import numpy as np
import cvxpy as cp
from scipy.optimize import minimize
from scipy.linalg import expm


# ---------------------------------------------------------------- states


def random_pure_states(n, d, rng):
    """Haar-random pure states as density matrices."""
    out = []
    for _ in range(n):
        v = rng.standard_normal(d) + 1j * rng.standard_normal(d)
        v /= np.linalg.norm(v)
        out.append(np.outer(v, v.conj()))
    return out


def clustered_pure_states(n, d, rng, spread):
    """Pure states = common direction + `spread` * noise (large pairwise
    overlap => exclusion value strictly positive => interesting region)."""
    base = rng.standard_normal(d) + 1j * rng.standard_normal(d)
    base /= np.linalg.norm(base)
    out = []
    for _ in range(n):
        g = rng.standard_normal(d) + 1j * rng.standard_normal(d)
        v = base + spread * g
        v /= np.linalg.norm(v)
        out.append(np.outer(v, v.conj()))
    return out


def random_mixed_states(n, d, rng, k=2):
    """Random rank-k mixed states (Hilbert-Schmidt-like)."""
    out = []
    for _ in range(n):
        G = rng.standard_normal((d, k)) + 1j * rng.standard_normal((d, k))
        rho = G @ G.conj().T
        out.append(rho / np.trace(rho).real)
    return out


# ---------------------------------------------------------------- SDP (POVM)


def sdp_exclusion(rhos, solver=cp.CLARABEL):
    n = len(rhos)
    d = rhos[0].shape[0]
    Ms = [cp.Variable((d, d), hermitian=True) for _ in range(n)]
    cons = [M >> 0 for M in Ms] + [sum(Ms) == np.eye(d)]
    obj = cp.Minimize(cp.real(sum(cp.trace(rhos[i] @ Ms[i]) for i in range(n))))
    prob = cp.Problem(obj, cons)
    prob.solve(solver=solver)
    return max(prob.value, 0.0)


# ---------------------------------------------------- QCQP (projective, n=d)


def _proj_value_from_unitary(U, rhos):
    return sum((U[:, i].conj() @ rhos[i] @ U[:, i]).real for i in range(len(rhos)))


def qcqp_unitary(rhos, rng, restarts=8):
    """Minimize over orthonormal bases via U = expm(iH), H hermitian.

    Unconstrained in d^2 real parameters, so plain BFGS works and there are
    no equality constraints for the solver to violate. Column permutations
    are absorbed into U, so all assignments of vectors to states are covered.
    """
    n = len(rhos)
    d = rhos[0].shape[0]
    assert n == d
    iu = np.triu_indices(d, 1)

    def params_to_U(x):
        H = np.zeros((d, d), dtype=complex)
        H[np.diag_indices(d)] = x[:d]
        off = x[d : d + d * (d - 1) // 2] + 1j * x[d + d * (d - 1) // 2 :]
        H[iu] = off
        H = H + H.conj().T - np.diag(np.diag(H).real)
        return expm(1j * H)

    def f(x):
        return _proj_value_from_unitary(params_to_U(x), rhos)

    best = np.inf
    best_U = None
    for _ in range(restarts):
        x0 = rng.standard_normal(d * d) * 1.5
        res = minimize(f, x0, method="BFGS", options={"maxiter": 600, "gtol": 1e-10})
        if res.fun < best:
            best, best_U = res.fun, params_to_U(res.x)
    return best, best_U


def qcqp_slsqp(rhos, rng, restarts=8):
    """The user's original SLSQP formulation, for cross-checking."""
    n = len(rhos)
    d = rhos[0].shape[0]

    def unpack(x):
        return x[: n * d].reshape(d, n) + 1j * x[n * d :].reshape(d, n)

    def objective(x):
        V = unpack(x)
        return sum((V[:, i].conj() @ rhos[i] @ V[:, i]).real for i in range(n))

    def orthogonality(x):
        V = unpack(x)
        vals = [np.vdot(V[:, i], V[:, j]) for i in range(n) for j in range(i + 1, n)]
        return [v.real for v in vals] + [v.imag for v in vals]

    def normalization(x):
        V = unpack(x)
        return [np.vdot(V[:, i], V[:, i]).real - 1 for i in range(n)]

    cons = [{"type": "eq", "fun": orthogonality}, {"type": "eq", "fun": normalization}]

    best = np.inf
    for _ in range(restarts):
        x0 = rng.standard_normal(2 * n * d)
        res = minimize(objective, x0, method="SLSQP", constraints=cons, options={"maxiter": 400, "ftol": 1e-12})
        if res.success and res.fun < best:
            # verify feasibility before trusting the value
            if max(abs(c) for c in orthogonality(res.x)) < 1e-7 and max(abs(c) for c in normalization(res.x)) < 1e-7:
                best = min(best, res.fun)
    return best
