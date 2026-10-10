"""Scientific regression: sparse (Pauli-label) vs dense (matrix) agreement."""

from dataclasses import dataclass

import numpy as np
import pytest
from strategies.pauli_random import (
    ATOL,
    RTOL,
    _commutes,
    observable_labels,
    random_pauli_label,
    random_pauli_sum,
)
from strategies.shadow_agreement import (
    assert_core_agreement,
    assert_shadow_agreement,
    densify_hamiltonians,
    densify_operator_set,
)

from shadowsim.core import Hamiltonian, Operator, OperatorSet, PauliSum, State
from shadowsim.shadow import ShadowHamiltonian, run_shadow_simulation


def zero_state(n: int) -> State:
    """Return the computational ``|0…0⟩`` state on ``n`` qubits."""
    vec = np.zeros(2**n, dtype=np.complex128)
    vec[0] = 1.0
    return State(vec, n)


def _is_diagonal_pauli(label: str) -> bool:
    """Return whether ``label`` is diagonal in the computational basis (I/Z only)."""
    return set(label) <= {"I", "Z"}


def shadow_dynamics_applicable(
    hamiltonians: Hamiltonian | list[Hamiltonian],
    operator_set: OperatorSet,
    n_qubits: int,
    *,
    tol: float = 1e-10,
) -> bool:
    """Return whether ``run_shadow_simulation`` can run for ``|0…0⟩`` on this system.

    Requires closure size ≥ 2 (padded shadow space has ≥ 1 qubit) and shadow
    amplitude weight ``A = Σ|⟨O⟩|² == 1`` so :class:`ShadowState` is normalized.
    """
    shadow = ShadowHamiltonian(operator_set, hamiltonians, num_qubits=n_qubits, tol=tol)
    if len(shadow.basis) < 2:
        return False
    psi = zero_state(n_qubits).get_state()
    weight = 0.0
    for lab in shadow.basis:
        exp = complex(np.vdot(psi, Operator(lab).matrix @ psi))
        weight += abs(exp) ** 2
    return bool(np.isclose(weight, 1.0))


def assert_dynamics_agreement(
    hamiltonians: Hamiltonian | list[Hamiltonian],
    operator_set: OperatorSet,
    n_qubits: int,
    *,
    total_time: float = 0.5,
    time_steps: int = 5,
    tol: float = 1e-10,
) -> None:
    """Compare short QuTiP trajectories for sparse vs densified inputs."""
    assert shadow_dynamics_applicable(hamiltonians, operator_set, n_qubits, tol=tol), (
        "dynamics comparison requires basis size >= 2 and unit shadow weight on |0…0⟩"
    )
    state = zero_state(n_qubits)
    sparse_result = run_shadow_simulation(
        hamiltonians,
        operator_set,
        state,
        total_time=total_time,
        time_steps=time_steps,
        num_qubits=n_qubits,
        tol=tol,
    )
    dense_result = run_shadow_simulation(
        densify_hamiltonians(hamiltonians),
        densify_operator_set(operator_set),
        state,
        total_time=total_time,
        time_steps=time_steps,
        num_qubits=n_qubits,
        tol=tol,
    )

    assert sparse_result.shadow_hamiltonian.used_sparse_pauli_path is True
    assert dense_result.shadow_hamiltonian.used_sparse_pauli_path is False
    assert np.allclose(
        sparse_result.shadow_hamiltonian.H_S,
        dense_result.shadow_hamiltonian.H_S,
        atol=ATOL,
        rtol=RTOL,
    )
    assert np.allclose(sparse_result.H_S_padded, dense_result.H_S_padded, atol=ATOL, rtol=RTOL)
    assert sparse_result.shadow_num_qubits == dense_result.shadow_num_qubits
    assert sparse_result.labels == dense_result.labels
    assert len(sparse_result.expectations) == len(dense_result.expectations)
    for left, right in zip(sparse_result.expectations, dense_result.expectations, strict=True):
        assert np.allclose(left, right, atol=ATOL, rtol=RTOL)


@dataclass(frozen=True)
class RegressionCase:
    """One reproducible sparse↔dense comparison case."""

    id: str
    n_qubits: int
    seed: int
    n_terms: int
    n_obs: int
    scale: float
    commuting: bool | None
    compare_dynamics: bool

    def build_sparse(self) -> tuple[Hamiltonian, OperatorSet]:
        rng = np.random.default_rng(self.seed)
        ps = random_pauli_sum(
            rng,
            self.n_qubits,
            self.n_terms,
            self.scale,
            commuting=self.commuting,
        )
        if self.compare_dynamics:
            # One computational-diagonal observable (⟨·⟩=±1 on |0…0⟩) plus
            # non-diagonal labels so H typically enlarges the closure to m≥2.
            z_lab = "Z" + "I" * (self.n_qubits - 1)
            obs = [z_lab]
            while len(obs) < self.n_obs:
                lab = random_pauli_label(rng, self.n_qubits)
                if lab not in obs and not _is_diagonal_pauli(lab):
                    obs.append(lab)
            # Ensure H does not all-commute with z_lab so closure size grows.
            x_lab = "X" + "I" * (self.n_qubits - 1)
            terms = dict(ps.terms)
            if all(_commutes(lab, z_lab) for lab in terms):
                terms[x_lab] = terms.get(x_lab, 0.0) + self.scale
                ps = PauliSum(terms)
            return Hamiltonian(ps), OperatorSet(obs)

        obs = observable_labels(rng, self.n_qubits, self.n_obs)
        return Hamiltonian(ps), OperatorSet(obs)


def _build_regression_cases() -> list[RegressionCase]:
    """Curated axis coverage (~20 cases), not a full Cartesian product."""
    specs: list[tuple[int, bool | None, int, int, float, int, bool]] = [
        # n, commuting, n_terms, n_obs, scale, seed, compare_dynamics
        (1, True, 1, 1, 1.0, 1, True),
        (1, False, 2, 1, 1.0, 2, True),
        (1, False, 2, 1, 1e-3, 3, True),
        (1, False, 3, 1, 1e3, 4, True),
        (2, True, 2, 2, 1.0, 10, True),
        (2, True, 5, 2, 1.0, 11, True),
        (2, False, 2, 2, 1.0, 12, True),
        (2, False, 5, 2, 1e-3, 13, True),
        (2, False, 5, 2, 1e3, 14, True),
        (3, True, 2, 2, 1.0, 20, True),
        (3, True, 5, 3, 1.0, 21, True),
        (3, False, 2, 2, 1.0, 22, True),
        (3, False, 5, 3, 1.0, 23, True),
        (3, False, 5, 2, 1e-3, 24, False),
        (3, False, 5, 2, 1e3, 25, False),
        (4, True, 2, 2, 1.0, 30, True),
        (4, False, 2, 2, 1.0, 31, True),
        (4, False, 3, 2, 1.0, 32, False),
        (4, True, 3, 2, 1e-3, 33, False),
        (4, False, 2, 2, 1e3, 34, False),
    ]
    cases: list[RegressionCase] = []
    for n, commuting, n_terms, n_obs, scale, seed, dynamics in specs:
        flag = "comm" if commuting is True else "noncomm" if commuting is False else "any"
        case_id = f"n{n}_{flag}_t{n_terms}_o{n_obs}_s{scale:g}_seed{seed}"
        cases.append(
            RegressionCase(
                id=case_id,
                n_qubits=n,
                seed=seed,
                n_terms=n_terms,
                n_obs=n_obs,
                scale=scale,
                commuting=commuting,
                compare_dynamics=dynamics,
            )
        )
    return cases


REGRESSION_CASES = _build_regression_cases()


@pytest.mark.parametrize("case", REGRESSION_CASES, ids=lambda c: c.id)
def test_sparse_dense_regression_case(case: RegressionCase):
    hamiltonians, operator_set = case.build_sparse()
    assert_core_agreement(hamiltonians, operator_set)
    assert_shadow_agreement(hamiltonians, operator_set)


@pytest.mark.qutip
@pytest.mark.parametrize(
    "case",
    [c for c in REGRESSION_CASES if c.compare_dynamics],
    ids=lambda c: c.id,
)
def test_sparse_dense_dynamics_case(case: RegressionCase):
    pytest.importorskip("qutip")
    hamiltonians, operator_set = case.build_sparse()
    if shadow_dynamics_applicable(hamiltonians, operator_set, case.n_qubits):
        assert_dynamics_agreement(hamiltonians, operator_set, case.n_qubits)


def test_canonical_one_qubit_x_z_seed():
    """Canonical H=X, ops={Z} agrees across paths (oracle seed)."""
    h = Hamiltonian("X")
    ops = OperatorSet(["Z"])
    assert_core_agreement(h, ops)
    sparse, dense = assert_shadow_agreement(h, ops)
    expected = np.array([[0, -2j], [2j, 0]], dtype=np.complex128)
    assert np.allclose(sparse.H_S, expected, atol=ATOL, rtol=RTOL)
    assert np.allclose(dense.H_S, expected, atol=ATOL, rtol=RTOL)


@pytest.mark.qutip
def test_canonical_one_qubit_x_z_seed_dynamics():
    pytest.importorskip("qutip")
    assert_dynamics_agreement(Hamiltonian("X"), OperatorSet(["Z"]), 1)


def test_identity_hamiltonian_near_zero_h_s():
    """Identity H yields a trivial (zero) shadow Hamiltonian for both paths."""
    h = Hamiltonian("I")
    ops = OperatorSet(["Z"])
    assert_core_agreement(h, ops)
    sparse, dense = assert_shadow_agreement(h, ops)
    assert sparse.basis == dense.basis == ["Z"]
    assert np.allclose(sparse.H_S, 0.0, atol=ATOL)
    assert np.allclose(dense.H_S, 0.0, atol=ATOL)
    # Closure size 1 → padded shadow space has 0 qubits; dynamics not applicable.
    assert not shadow_dynamics_applicable(h, ops, 1)


def test_commuting_two_qubit_hamiltonian_sparse_closure():
    """Fully commuting H = ZI + IZ with observable ZI keeps a small closure."""
    h = Hamiltonian(PauliSum({"ZI": 1.0, "IZ": 0.5}))
    ops = OperatorSet(["ZI"])
    assert_core_agreement(h, ops)
    sparse, _dense = assert_shadow_agreement(h, ops)
    assert sparse.operator_pauli_closure == {"ZI"}
    assert np.allclose(sparse.H_S, 0.0, atol=ATOL)
    assert not shadow_dynamics_applicable(h, ops, 2)


def test_partial_canceling_hamiltonian_terms():
    """Overlapping terms that partially cancel agree after merge."""
    terms = [
        Hamiltonian("X"),
        Hamiltonian(PauliSum({"X": -1.0, "Z": 0.5})),
    ]
    ops = OperatorSet(["X", "Z"])
    assert_core_agreement(terms, ops)
    sparse, dense = assert_shadow_agreement(terms, ops)
    assert set(sparse.pauli_decomposition) == {"Z"}
    assert sparse.pauli_decomposition["Z"] == pytest.approx(0.5)
    assert dense.pauli_decomposition["Z"] == pytest.approx(0.5)


@pytest.mark.qutip
def test_partial_canceling_hamiltonian_terms_dynamics():
    pytest.importorskip("qutip")
    terms = [
        Hamiltonian("X"),
        Hamiltonian(PauliSum({"X": -1.0, "Z": 0.5})),
    ]
    assert_dynamics_agreement(terms, OperatorSet(["X", "Z"]), 1)


def test_coefficients_near_shadow_tol():
    """Coeffs just above/below default tol filter consistently on both paths."""
    tol = 1e-10
    above = Hamiltonian(PauliSum({"X": 1.0, "Z": 5e-10}))
    below = Hamiltonian(PauliSum({"X": 1.0, "Z": 1e-11}))
    ops = OperatorSet(["Y"])

    sparse_above, dense_above = assert_shadow_agreement(above, ops, tol=tol)
    assert "Z" in sparse_above.pauli_decomposition
    assert "Z" in dense_above.pauli_decomposition

    sparse_below, dense_below = assert_shadow_agreement(below, ops, tol=tol)
    assert "Z" not in sparse_below.pauli_decomposition
    assert "Z" not in dense_below.pauli_decomposition
    assert set(sparse_below.pauli_decomposition) == set(dense_below.pauli_decomposition) == {"X"}


def test_identical_support_merge_in_expression():
    """Repeated labels in an expression merge before densification."""
    h = Hamiltonian("X + 2*X")
    ops = OperatorSet(["Z"])
    assert h.pauli_sum is not None
    assert h.pauli_sum.terms == {"X": 3 + 0j}
    assert_core_agreement(h, ops)
    sparse, dense = assert_shadow_agreement(h, ops)
    assert sparse.pauli_decomposition["X"] == pytest.approx(3 + 0j)
    assert dense.pauli_decomposition["X"] == pytest.approx(3 + 0j)


@pytest.mark.qutip
def test_identical_support_merge_in_expression_dynamics():
    pytest.importorskip("qutip")
    assert_dynamics_agreement(Hamiltonian("X + 2*X"), OperatorSet(["Z"]), 1)


def test_random_pauli_string_observables_one_to_four_qubits():
    """Random Pauli-string observables densify and shadow-agree for n=1..4."""
    for n, seed in ((1, 100), (2, 101), (3, 102), (4, 103)):
        rng = np.random.default_rng(seed)
        ps = random_pauli_sum(rng, n, n_terms=min(3, 4**n - 1), scale=1.0, commuting=None)
        obs = observable_labels(rng, n, k=min(2, 4**n - 1))
        h = Hamiltonian(ps)
        ops = OperatorSet(obs)
        assert_core_agreement(h, ops)
        assert_shadow_agreement(h, ops)
