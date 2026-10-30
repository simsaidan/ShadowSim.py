"""Unit tests for the Jaynes–Cummings–Hubbard model factory."""

from dataclasses import fields

import numpy as np
import pytest

from shadowsim.models import (
    JaynesCummingsHubbardModel,
    TavisCummingsHubbardModel,
    jaynes_cummings,
    jaynes_cummings_hubbard,
    tavis_cummings_hubbard,
)


def _assert_same_operators(got: JaynesCummingsHubbardModel, expected: TavisCummingsHubbardModel) -> None:
    """Compare operator payloads; dataclass equality is type-sensitive."""
    assert got.n_cavities == expected.n_cavities
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


def test_one_cavity_matches_jaynes_cummings_and_tavis_cummings_hubbard():
    model = jaynes_cummings_hubbard()

    assert isinstance(model, JaynesCummingsHubbardModel)
    assert isinstance(model, TavisCummingsHubbardModel)
    assert model.n_cavities == 1
    assert model.n_emitters == 1
    assert model.num_qubits == 3
    _assert_same_operators(model, tavis_cummings_hubbard())
    np.testing.assert_allclose(model.psi0.to_numpy(), jaynes_cummings().psi0.to_numpy())
    assert [h.sites for h in model.local_hamiltonians] == [h.sites for h in jaynes_cummings().local_hamiltonians]


def test_one_cavity_ignores_hopping():
    model = jaynes_cummings_hubbard(nu="unused")
    _assert_same_operators(model, tavis_cummings_hubbard())


def test_two_cavities_match_tavis_cummings_hubbard():
    nu = 1 + 2j
    model = jaynes_cummings_hubbard(n_cavities=2, nu=nu, g=50.0)

    assert model.n_cavities == 2
    assert model.num_qubits == 6
    _assert_same_operators(model, tavis_cummings_hubbard(n_cavities=2, n_emitters=1, nu=nu, g=50.0))


@pytest.mark.parametrize("name", ["g", "gamma", "omega_e"])
def test_per_emitter_sequences_rejected(name):
    with pytest.raises(ValueError, match=f"{name} must be a scalar"):
        jaynes_cummings_hubbard(**{name: [1.0, 2.0]})


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"cavity_levels": 8}, "cavity_levels=4"),
        ({"initial_fock": 5}, "initial_fock"),
        ({"n_cavities": 0}, "n_cavities"),
        ({"n_cavities": 2, "nu": [1.0, 2.0]}, "nu"),
    ],
)
def test_parent_validation_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        jaynes_cummings_hubbard(**kwargs)


def test_direct_construction_rejects_multiple_emitters():
    base = tavis_cummings_hubbard(n_cavities=2, n_emitters=2)
    payload = {field.name: getattr(base, field.name) for field in fields(TavisCummingsHubbardModel)}
    with pytest.raises(ValueError, match="n_emitters must be 1"):
        JaynesCummingsHubbardModel(**payload)
