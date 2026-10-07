"""Unit tests for the classical / transverse-field Ising model factory."""

import numpy as np
import pytest

from shadowsim.core import PauliString
from shadowsim.models import IsingModel, ising
from shadowsim.simulators import population_one
from shadowsim.utils import tensor


def _hand_ising_matrix(n: int, j: float, h: float, edges: list[tuple[int, int]], field: str) -> np.ndarray:
    """Independently build a dense Ising Hamiltonian via Kronecker products."""
    i2 = np.eye(2, dtype=np.complex128)
    x = PauliString.from_string("X").matrix()
    z = PauliString.from_string("Z").matrix()
    field_op = z if field == "classical" else x

    dim = 2**n
    h_mat = np.zeros((dim, dim), dtype=np.complex128)

    for a, b in edges:
        ops = [i2] * n
        ops[a] = z
        ops[b] = z
        h_mat = h_mat + j * tensor(ops)

    for site in range(n):
        ops = [i2] * n
        ops[site] = field_op
        h_mat = h_mat + h * tensor(ops)

    return h_mat


def test_open_chain_metadata_and_terms():
    model = ising(n_qubits=3, J=1.0, h=0.5, field="transverse", boundary="open")

    assert isinstance(model, IsingModel)
    assert model.num_qubits == 3
    assert model.edges == [(0, 1), (1, 2)]
    assert model.topology == "chain"
    assert model.boundary == "open"
    assert model.field == "transverse"
    assert model.J == 1.0
    assert model.h == 0.5
    assert model.c_ops_full == []
    assert model.c_ops_local == []
    assert model.measurement_groups == [0, 1, 2]
    assert list(model.reducers) == [population_one, population_one, population_one]

    terms = model.pauli_sum.terms
    assert terms["ZZI"] == pytest.approx(1.0)
    assert terms["IZZ"] == pytest.approx(1.0)
    assert terms["XII"] == pytest.approx(0.5)
    assert terms["IXI"] == pytest.approx(0.5)
    assert terms["IIX"] == pytest.approx(0.5)
    assert model.pauli_sum.is_hermitian()


def test_classical_field_uses_z():
    model = ising(n_qubits=2, J=1.0, h=0.25, field="classical")
    terms = model.pauli_sum.terms
    assert set(terms) == {"ZZ", "ZI", "IZ"}
    assert terms["ZZ"] == pytest.approx(1.0)
    assert terms["ZI"] == pytest.approx(0.25)
    assert terms["IZ"] == pytest.approx(0.25)
    np.testing.assert_allclose(model.psi0.to_numpy(), np.array([1, 0, 0, 0], dtype=np.complex128))


def test_transverse_psi0_is_all_plus():
    model = ising(n_qubits=2, J=1.0, h=0.0, field="transverse")
    plus = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2.0)
    np.testing.assert_allclose(model.psi0.to_numpy(), tensor([plus, plus]))


def test_periodic_wrap_in_full_not_local():
    model = ising(n_qubits=4, J=1.0, h=0.0, boundary="periodic")

    assert model.edges == [(0, 1), (1, 2), (2, 3), (0, 3)]
    assert "ZIIZ" in model.pauli_sum.terms
    assert model.pauli_sum.terms["ZIIZ"] == pytest.approx(1.0)

    local_sites = [tuple(h.sites) for h in model.local_hamiltonians]
    assert local_sites == [(0, 1), (1, 2), (2, 3)]
    assert (0, 3) not in local_sites
    assert len(model.full_hamiltonians) == 4


def test_custom_edges_and_noncontiguous_local_omission():
    edges = [(0, 1), (1, 4), (0, 3)]
    model = ising(n_qubits=5, J=1.0, h=0.2, field="classical", edges=edges)

    assert model.topology == "custom"
    assert model.boundary == "open"
    assert model.edges == [(0, 1), (1, 4), (0, 3)]

    local_sites = [tuple(h.sites) for h in model.local_hamiltonians]
    assert (0, 1) in local_sites
    assert (1, 4) not in local_sites
    assert (0, 3) not in local_sites
    assert model.pauli_sum.terms["IZIIZ"] == pytest.approx(1.0)
    assert model.pauli_sum.terms["ZIIZI"] == pytest.approx(1.0)


def test_custom_edges_conflict_with_boundary():
    with pytest.raises(ValueError, match="edges cannot be combined"):
        ising(n_qubits=3, edges=[(0, 1)], boundary="periodic")


def test_custom_edges_normalize_order_and_reject_duplicates():
    model = ising(n_qubits=3, J=1.0, edges=[(1, 0), (2, 1)])
    assert model.edges == [(0, 1), (1, 2)]

    with pytest.raises(ValueError, match="duplicate edge"):
        ising(n_qubits=3, J=1.0, edges=[(0, 1), (1, 0)])


def test_zero_field_and_zero_coupling_limits():
    zero_h = ising(n_qubits=3, J=1.5, h=0.0, field="transverse")
    assert set(zero_h.pauli_sum.terms) == {"ZZI", "IZZ"}
    assert all(c == pytest.approx(1.5) for c in zero_h.pauli_sum.terms.values())
    assert all(len(h.sites) == 2 for h in zero_h.local_hamiltonians)

    zero_j = ising(n_qubits=3, J=0.0, h=0.7, field="classical")
    assert set(zero_j.pauli_sum.terms) == {"ZII", "IZI", "IIZ"}
    assert all(c == pytest.approx(0.7) for c in zero_j.pauli_sum.terms.values())
    assert all(h.sites == [i] for i, h in enumerate(zero_j.local_hamiltonians))


def test_dense_matrix_matches_independent_construction():
    for n, j, h, field, boundary in (
        (2, 1.0, 0.3, "transverse", "open"),
        (3, 0.8, 0.4, "classical", "open"),
        (3, 1.0, 0.0, "transverse", "periodic"),
    ):
        model = ising(n_qubits=n, J=j, h=h, field=field, boundary=boundary)
        expected = _hand_ising_matrix(n, j, h, model.edges, field)
        np.testing.assert_allclose(model.hamiltonian.matrix, expected)
        # Sum of full terms matches the combined Hamiltonian.
        summed = sum((term.matrix for term in model.full_hamiltonians), start=np.zeros_like(expected))
        np.testing.assert_allclose(summed, expected)


def test_hermiticity():
    for field in ("classical", "transverse"):
        model = ising(n_qubits=4, J=1.0, h=0.5, field=field, boundary="periodic")
        assert model.pauli_sum.is_hermitian()
        mat = model.hamiltonian.matrix
        np.testing.assert_allclose(mat, mat.conjugate().T)


def test_validation_errors():
    with pytest.raises(ValueError, match="n_qubits"):
        ising(n_qubits=1)
    with pytest.raises(ValueError, match="periodic boundary requires"):
        ising(n_qubits=2, boundary="periodic")
    with pytest.raises(ValueError, match="field must be"):
        ising(n_qubits=2, field="diagonal")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="J and h cannot both be zero"):
        ising(n_qubits=2, J=0.0, h=0.0)
    with pytest.raises(ValueError, match="no terms"):
        ising(n_qubits=3, J=1.0, h=0.0, edges=[])
    with pytest.raises(ValueError, match="self-loop"):
        ising(n_qubits=3, J=1.0, edges=[(1, 1)])
    with pytest.raises(ValueError, match="out of range"):
        ising(n_qubits=3, J=1.0, edges=[(0, 3)])
    with pytest.raises(ValueError, match="unsupported topology"):
        ising(n_qubits=3, topology="custom")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported boundary"):
        ising(n_qubits=3, boundary="reflecting")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="each edge must be a pair"):
        ising(n_qubits=3, J=1.0, edges=[[0, 1]])  # type: ignore[list-item]
