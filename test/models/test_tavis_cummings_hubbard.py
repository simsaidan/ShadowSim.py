"""Unit tests for the Tavis–Cummings–Hubbard model factory."""

import numpy as np
import pytest

from shadowsim.models import TavisCummingsHubbardModel, TavisCummingsModel, tavis_cummings, tavis_cummings_hubbard
from shadowsim.simulators import Measurement
from shadowsim.utils.constants import (
    I,
    one_state_two_qubits,
    three_state_two_qubits,
    two_state_two_qubits,
    zero_state_two_qubits,
)
from shadowsim.utils.tensor import tensor


def _assert_same_operators(got: TavisCummingsHubbardModel, expected: TavisCummingsModel) -> None:
    """Compare operator payloads; dataclass equality is type-sensitive."""
    assert got.n_emitters == expected.n_emitters
    assert got.num_qubits == expected.num_qubits
    assert got.measurements == expected.measurements

    assert [h.sites for h in got.local_hamiltonians] == [h.sites for h in expected.local_hamiltonians]
    for actual, reference in zip(got.local_hamiltonians, expected.local_hamiltonians, strict=True):
        np.testing.assert_allclose(actual.matrix, reference.matrix)

    for actual, reference in zip(got.full_hamiltonians, expected.full_hamiltonians, strict=True):
        np.testing.assert_allclose(actual.matrix, reference.matrix)

    assert [op.sites for op in got.c_ops_local] == [op.sites for op in expected.c_ops_local]
    for actual, reference in zip(got.c_ops_local, expected.c_ops_local, strict=True):
        np.testing.assert_allclose(actual.matrix, reference.matrix)

    for actual, reference in zip(got.c_ops_full, expected.c_ops_full, strict=True):
        np.testing.assert_allclose(actual.matrix, reference.matrix)

    np.testing.assert_allclose(got.psi0.to_numpy(), expected.psi0.to_numpy())
    for actual, reference in zip(got.e_ops, expected.e_ops, strict=True):
        np.testing.assert_allclose(actual.matrix, reference.matrix)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"n_emitters": 2, "g": [100.0, 50.0], "gamma": [0.1, 0.2], "omega_e": [1.0, 2.0]},
        {"initial_fock": 0, "n_emitters": 3, "g": 10.0, "gamma": 0.5, "omega_e": 7.0},
        {"g": 200, "kappa": 2 * np.sqrt(24.5)},
    ],
)
def test_matches_tavis_cummings(kwargs):
    model = tavis_cummings_hubbard(**kwargs)

    assert isinstance(model, TavisCummingsHubbardModel)
    assert isinstance(model, TavisCummingsModel)
    assert model.n_cavities == 1
    _assert_same_operators(model, tavis_cummings(**kwargs))


def test_one_cavity_ignores_hopping():
    model = tavis_cummings_hubbard(nu=3 + 4j)
    _assert_same_operators(model, tavis_cummings())


def _lowering():
    return (
        np.outer(zero_state_two_qubits, one_state_two_qubits)
        + np.sqrt(2) * np.outer(one_state_two_qubits, two_state_two_qubits)
        + np.sqrt(3) * np.outer(two_state_two_qubits, three_state_two_qubits)
    )


def test_two_cavities_without_hopping_are_disjoint_copies():
    kwargs = {"n_emitters": 1, "g": 10.0, "gamma": 0.2, "omega_e": 3.0, "omega_c": 4.0, "kappa": 0.5, "initial_fock": 1}
    block = tavis_cummings(**kwargs)
    model = tavis_cummings_hubbard(n_cavities=2, nu=0.0, **kwargs)
    width = block.num_qubits
    terms = len(block.local_hamiltonians)

    assert model.n_cavities == 2
    assert model.n_emitters == 1
    assert model.num_qubits == 6
    assert len(model.local_hamiltonians) == 2 * terms
    assert len(model.full_hamiltonians) == 2 * len(block.full_hamiltonians)
    assert len(model.c_ops_local) == 2 * len(block.c_ops_local)
    assert model.measurements == [
        Measurement.cavity_population(0, 1),
        Measurement.population(2),
        Measurement.cavity_population(3, 4),
        Measurement.population(5),
    ]
    np.testing.assert_allclose(model.psi0.to_numpy(), tensor([block.psi0.to_numpy(), block.psi0.to_numpy()]))

    for cavity in range(2):
        offset = cavity * width
        for got, expected in zip(
            model.local_hamiltonians[cavity * terms : (cavity + 1) * terms],
            block.local_hamiltonians,
            strict=True,
        ):
            assert got.sites == [site + offset for site in expected.sites]
            np.testing.assert_allclose(got.matrix, expected.matrix)
        for got, expected in zip(
            model.c_ops_local[cavity * len(block.c_ops_local) : (cavity + 1) * len(block.c_ops_local)],
            block.c_ops_local,
            strict=True,
        ):
            assert got.sites == [site + offset for site in expected.sites]
            np.testing.assert_allclose(got.matrix, expected.matrix)


def test_hopping_couples_the_two_fock_pairs():
    nu = 1 + 2j
    model = tavis_cummings_hubbard(n_cavities=2, n_emitters=1, nu=nu)
    a = _lowering()
    expected = nu * tensor([a.conjugate().T, I, a]) + np.conjugate(nu) * tensor([a, I, a.conjugate().T])

    hop = model.local_hamiltonians[-1]
    assert hop.sites == [0, 1, 2, 3, 4]
    np.testing.assert_allclose(hop.matrix, expected)
    np.testing.assert_allclose(model.full_hamiltonians[-1].matrix, tensor([expected, I]))
    assert len(model.local_hamiltonians) == 7


def test_pair_sequence_skips_zero_and_orders_pairs():
    model = tavis_cummings_hubbard(n_cavities=3, n_emitters=1, nu=[1.0, 0.0, 2.0])
    hops = model.local_hamiltonians[-2:]

    assert [hop.sites for hop in hops] == [list(range(0, 5)), list(range(3, 8))]
    assert len(model.local_hamiltonians) == 11
    np.testing.assert_allclose(hops[1].matrix, 2 * hops[0].matrix)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"cavity_levels": 8}, "cavity_levels=4"),
        ({"initial_fock": 5}, "initial_fock"),
        ({"n_emitters": 0}, "n_emitters"),
        ({"n_emitters": 2, "g": [1.0]}, "g must be"),
        ({"n_emitters": 2, "gamma": [1.0, 2.0, 3.0]}, "gamma must be"),
        ({"n_emitters": 2, "omega_e": [1.0]}, "omega_e must be"),
        ({"n_cavities": 0}, "n_cavities"),
        ({"n_cavities": True}, "n_cavities"),
        ({"n_cavities": 2, "nu": [1.0, 2.0]}, "nu must be"),
        ({"n_cavities": 2, "nu": [True]}, "nu must be"),
        ({"n_cavities": 2, "nu": "1"}, "nu must be"),
    ],
)
def test_validation_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        tavis_cummings_hubbard(**kwargs)
