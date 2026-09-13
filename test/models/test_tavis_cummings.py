"""Unit tests for the Tavis–Cummings model factory."""

import numpy as np
import pytest

from shadowsim.models import TavisCummingsModel, tavis_cummings
from shadowsim.simulators import cavity_population, population_one
from shadowsim.utils import (
    I,
    one_state_two_qubits,
    tensor,
    three_state_two_qubits,
    two_state_two_qubits,
    zero_state_two_qubits,
)


def _example2_reference_operators():
    """Operator soup matching examples/simple_algo_benchmark.py (n_emitters=1)."""
    omega_c = 245000
    omega_e = 245000
    kappa = np.sqrt(24.5)
    gamma = np.sqrt(0.4)
    g = 100

    a = (
        np.outer(zero_state_two_qubits, one_state_two_qubits)
        + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
        + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
    )
    zero = np.array([1, 0], dtype=np.complex128)
    one = np.array([0, 1], dtype=np.complex128)
    sigma = np.outer(zero, one)

    h1 = omega_c * a.conjugate().T @ a
    h2 = omega_e * np.outer(one, one)
    h3 = g * (np.kron(a, sigma.conjugate().T) + np.kron(a.conjugate().T, sigma))

    return {
        "local_mats": [h1, h2, h3],
        "local_sites": [[0, 1], [2], [0, 1, 2]],
        "full_mats": [tensor([h1, I]), tensor([I, I, h2]), h3],
        "c_full": [kappa * np.kron(a, I), gamma * tensor([I, I, sigma])],
        "c_local_mats": [kappa * a, gamma * sigma],
        "c_local_sites": [[0, 1], [2]],
        "psi0": tensor([two_state_two_qubits, zero]),
        "e_ops": [
            tensor([a.conjugate().T @ a, I]),
            tensor([I, I, sigma.conjugate().T @ sigma]),
        ],
    }


def test_defaults_match_example2():
    model = tavis_cummings()
    ref = _example2_reference_operators()

    assert isinstance(model, TavisCummingsModel)
    assert model.n_emitters == 1
    assert model.num_qubits == 3
    assert model.measurement_groups == [[1, 2], 3]
    assert list(model.reducers) == [cavity_population, population_one]

    assert [h.sites for h in model.local_hamiltonians] == ref["local_sites"]
    for got, expected in zip(model.local_hamiltonians, ref["local_mats"], strict=True):
        np.testing.assert_allclose(got.matrix, expected)

    for got, expected in zip(model.full_hamiltonians, ref["full_mats"], strict=True):
        np.testing.assert_allclose(got.matrix, expected)

    assert [op.sites for op in model.c_ops_local] == ref["c_local_sites"]
    for got, expected in zip(model.c_ops_local, ref["c_local_mats"], strict=True):
        np.testing.assert_allclose(got.matrix, expected)

    for got, expected in zip(model.c_ops_full, ref["c_full"], strict=True):
        np.testing.assert_allclose(got.matrix, expected)

    np.testing.assert_allclose(model.psi0.to_numpy(), ref["psi0"])
    for got, expected in zip(model.e_ops, ref["e_ops"], strict=True):
        np.testing.assert_allclose(got.matrix, expected)


def test_psi0_initial_fock_and_ground_emitters():
    zero = np.array([1, 0], dtype=np.complex128)
    for fock, cavity_state in enumerate(
        (zero_state_two_qubits, one_state_two_qubits, two_state_two_qubits, three_state_two_qubits)
    ):
        model = tavis_cummings(initial_fock=fock, n_emitters=2)
        expected = tensor([cavity_state, zero, zero])
        np.testing.assert_allclose(model.psi0.to_numpy(), expected)
        assert model.psi0.get_num_qubits() == 4


def test_g_and_kappa_scale_operator_norms():
    base = tavis_cummings(g=100, kappa=np.sqrt(24.5))
    scaled = tavis_cummings(g=200, kappa=2 * np.sqrt(24.5))

    # Coupling is the third local Hamiltonian for n_emitters=1.
    assert np.isclose(
        np.linalg.norm(scaled.local_hamiltonians[2].matrix),
        2 * np.linalg.norm(base.local_hamiltonians[2].matrix),
    )
    # Cavity Lindblad is the first c_op.
    assert np.isclose(
        np.linalg.norm(scaled.c_ops_local[0].matrix),
        2 * np.linalg.norm(base.c_ops_local[0].matrix),
    )


def test_two_emitters_layout_and_observables():
    model = tavis_cummings(n_emitters=2, g=[100.0, 50.0], gamma=[0.1, 0.2], omega_e=[1.0, 2.0])

    assert model.n_emitters == 2
    assert model.num_qubits == 4
    assert model.measurement_groups == [[1, 2], 3, 4]
    assert list(model.reducers) == [cavity_population, population_one, population_one]
    assert len(model.e_ops) == 3
    assert len(model.c_ops_local) == 3
    # cavity + (emitter free + coupling) * 2
    assert len(model.local_hamiltonians) == 5
    assert [h.sites for h in model.local_hamiltonians] == [
        [0, 1],
        [2],
        [0, 1, 2],
        [3],
        [0, 1, 2, 3],
    ]
    assert model.local_hamiltonians[4].matrix.shape == (16, 16)
    assert model.full_hamiltonians[0].matrix.shape == (16, 16)
    assert model.psi0.to_numpy().shape == (16,)

    # Per-emitter omega_e / gamma scale same-sized local operators.
    assert np.isclose(
        np.linalg.norm(model.local_hamiltonians[3].matrix) / np.linalg.norm(model.local_hamiltonians[1].matrix),
        2.0,
    )
    assert np.isclose(
        np.linalg.norm(model.c_ops_local[2].matrix) / np.linalg.norm(model.c_ops_local[1].matrix),
        2.0,
    )

    # Per-emitter g: same emitter index, different g, same matrix shape.
    weak = tavis_cummings(n_emitters=2, g=[100.0, 25.0])
    strong = tavis_cummings(n_emitters=2, g=[100.0, 50.0])
    assert np.isclose(
        np.linalg.norm(strong.local_hamiltonians[4].matrix),
        2 * np.linalg.norm(weak.local_hamiltonians[4].matrix),
    )


def test_scalar_params_broadcast_to_emitters():
    model = tavis_cummings(n_emitters=3, g=10.0, gamma=0.5, omega_e=7.0)
    # Same-sized per-emitter locals (2x2) should match under scalar broadcast.
    free_norms = [np.linalg.norm(model.local_hamiltonians[i].matrix) for i in (1, 3, 5)]
    assert np.allclose(free_norms, free_norms[0])
    gamma_norms = [np.linalg.norm(op.matrix) for op in model.c_ops_local[1:]]
    assert np.allclose(gamma_norms, gamma_norms[0])
    assert model.measurement_groups == [[1, 2], 3, 4, 5]
    assert len(model.reducers) == 4


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"cavity_levels": 8}, "cavity_levels=4"),
        ({"initial_fock": 5}, "initial_fock"),
        ({"n_emitters": 0}, "n_emitters"),
        ({"n_emitters": 2, "g": [1.0]}, "g must be"),
        ({"n_emitters": 2, "gamma": [1.0, 2.0, 3.0]}, "gamma must be"),
        ({"n_emitters": 2, "omega_e": [1.0]}, "omega_e must be"),
    ],
)
def test_validation_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        tavis_cummings(**kwargs)
