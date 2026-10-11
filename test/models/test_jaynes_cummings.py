"""Unit tests for the Jaynes–Cummings model factory."""

from dataclasses import fields

import numpy as np
import pytest

from shadowsim.models import JaynesCummingsModel, TavisCummingsModel, jaynes_cummings, tavis_cummings


def _assert_same_operators(got: JaynesCummingsModel, expected: TavisCummingsModel) -> None:
    """Compare operator payloads; dataclass equality is type-sensitive."""
    assert got.n_emitters == expected.n_emitters
    assert got.num_qubits == expected.num_qubits
    assert got.measurement_groups == expected.measurement_groups
    assert list(got.reducers) == list(expected.reducers)

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


def test_defaults_match_tavis_cummings():
    model = jaynes_cummings()

    assert isinstance(model, JaynesCummingsModel)
    assert isinstance(model, TavisCummingsModel)
    assert model.n_emitters == 1
    assert model.num_qubits == 3
    _assert_same_operators(model, tavis_cummings())


def test_g_and_kappa_scale_operator_norms():
    base = jaynes_cummings(g=100, kappa=np.sqrt(24.5))
    scaled = jaynes_cummings(g=200, kappa=2 * np.sqrt(24.5))

    assert np.isclose(
        np.linalg.norm(scaled.local_hamiltonians[2].matrix),
        2 * np.linalg.norm(base.local_hamiltonians[2].matrix),
    )
    assert np.isclose(
        np.linalg.norm(scaled.c_ops_local[0].matrix),
        2 * np.linalg.norm(base.c_ops_local[0].matrix),
    )


@pytest.mark.parametrize("name", ["g", "gamma", "omega_e"])
def test_per_emitter_sequences_rejected(name):
    with pytest.raises(ValueError, match=f"{name} must be a scalar"):
        jaynes_cummings(**{name: [1.0, 2.0]})


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"cavity_levels": 8}, "cavity_levels=4"),
        ({"initial_fock": 5}, "initial_fock"),
        ({"initial_fock": -1}, "initial_fock"),
    ],
)
def test_parent_validation_errors(kwargs, match):
    with pytest.raises(ValueError, match=match):
        jaynes_cummings(**kwargs)


def test_direct_construction_rejects_multiple_emitters():
    base = tavis_cummings(n_emitters=2)
    payload = {field.name: getattr(base, field.name) for field in fields(TavisCummingsModel)}
    with pytest.raises(ValueError, match="n_emitters must be 1"):
        JaynesCummingsModel(**payload)
