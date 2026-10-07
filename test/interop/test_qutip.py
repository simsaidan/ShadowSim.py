from types import SimpleNamespace

import numpy as np
import pytest
from qutip import Qobj, basis, destroy, sigmaz, spre, tensor

from shadowsim.core import DensityOperator, Hamiltonian, Operator, State
from shadowsim.interop import qutip as qutip_interop
from shadowsim.interop.qutip import from_qutip, to_qutip


def test_from_qutip_ket_to_state():
    psi = from_qutip(basis(2, 0))
    assert isinstance(psi, State)
    assert psi.get_num_qubits() == 1
    assert psi.get_local_dim() == 2
    assert np.allclose(psi.state, [1.0, 0.0])


def test_from_qutip_bra_to_state():
    psi = from_qutip(basis(2, 1).dag())
    assert isinstance(psi, State)
    assert np.allclose(psi.state, [0.0, 1.0])


def test_from_qutip_multi_qubit_dims():
    psi = from_qutip(tensor(basis(2, 0), basis(2, 1)))
    assert isinstance(psi, State)
    assert psi.get_num_qubits() == 2
    assert psi.get_local_dim() == 2
    assert np.allclose(psi.state, [0.0, 1.0, 0.0, 0.0])


def test_from_qutip_hermitian_oper_to_hamiltonian():
    h = from_qutip(sigmaz())
    assert isinstance(h, Hamiltonian)
    assert np.allclose(h.matrix, [[1.0, 0.0], [0.0, -1.0]])


def test_from_qutip_non_hermitian_oper_to_operator():
    op = from_qutip(destroy(2))
    assert isinstance(op, Operator)
    assert not isinstance(op, Hamiltonian)


def test_from_qutip_density_auto_detect():
    rho_q = basis(2, 0) * basis(2, 0).dag()
    rho = from_qutip(rho_q)
    assert isinstance(rho, DensityOperator)
    assert np.allclose(rho.matrix, [[1.0, 0.0], [0.0, 0.0]])


def test_from_qutip_kind_density_and_overrides():
    rho_q = basis(2, 0) * basis(2, 0).dag()
    assert isinstance(from_qutip(rho_q, kind="density"), DensityOperator)
    assert isinstance(from_qutip(rho_q, kind="hamiltonian"), Hamiltonian)
    op = from_qutip(rho_q, kind="operator")
    assert isinstance(op, Operator)
    assert not isinstance(op, DensityOperator)
    assert not isinstance(op, Hamiltonian)


def test_from_qutip_kind_operator_for_hermitian_observable():
    op = from_qutip(sigmaz(), kind="operator")
    assert isinstance(op, Operator)
    assert not isinstance(op, Hamiltonian)


def test_from_qutip_state_layout_override():
    psi = from_qutip(basis(4, 0), num_qubits=2, local_dim=2)
    assert psi.get_num_qubits() == 2
    assert psi.get_local_dim() == 2


def test_from_qutip_rejects_partial_layout_override():
    with pytest.raises(ValueError, match="provided together"):
        from_qutip(basis(2, 0), num_qubits=1)


def test_from_qutip_rejects_unequal_dims():
    ket = Qobj(np.array([[1.0], [0.0], [0.0], [0.0], [0.0], [0.0]], dtype=np.complex128), dims=[[2, 3], [1, 1]])
    with pytest.raises(ValueError, match="homogeneous local_dim"):
        from_qutip(ket)


def test_from_qutip_rejects_non_qobj_and_bad_kind():
    with pytest.raises(TypeError, match="qutip.Qobj"):
        from_qutip(np.eye(2))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="kind must be one of"):
        from_qutip(basis(2, 0), kind="bogus")  # type: ignore[arg-type]


def test_from_qutip_rejects_superoperator():
    with pytest.raises(ValueError, match="superoperators"):
        from_qutip(spre(sigmaz()))


def test_from_qutip_kind_mismatch_errors():
    with pytest.raises(ValueError, match="kind='state'"):
        from_qutip(sigmaz(), kind="state")
    with pytest.raises(ValueError, match="kind='hamiltonian'"):
        from_qutip(basis(2, 0), kind="hamiltonian")
    with pytest.raises(ValueError, match="kind='operator'"):
        from_qutip(basis(2, 0), kind="operator")
    with pytest.raises(ValueError, match="kind='density'"):
        from_qutip(basis(2, 0), kind="density")


def test_from_qutip_rejects_non_square_oper():
    rect = Qobj(np.ones((2, 3), dtype=np.complex128))
    with pytest.raises(ValueError, match="square oper"):
        from_qutip(rect, kind="hamiltonian")
    with pytest.raises(ValueError, match="square oper"):
        from_qutip(rect, kind="operator")
    with pytest.raises(ValueError, match="square oper"):
        from_qutip(rect, kind="density")


def test_infer_kind_rejects_unsupported_qobj_type():
    with pytest.raises(ValueError, match="unsupported QuTiP Qobj type"):
        qutip_interop._infer_kind(SimpleNamespace(isket=False, isbra=False, isoper=False, type="other"))


def test_resolve_state_layout_rejects_empty_factors():
    with pytest.raises(ValueError, match="empty QuTiP dims"):
        qutip_interop._resolve_state_layout([], num_qubits=None, local_dim=None)


def test_to_qutip_state_and_operators():
    psi = State(np.array([1.0, 0.0], dtype=np.complex128), 1)
    qpsi = to_qutip(psi)
    assert qpsi.isket
    assert qpsi.dims == [[2], [1]]

    two_qubit = State(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.complex128), 2)
    assert to_qutip(two_qubit).dims == [[4], [1]]

    h = Hamiltonian(np.diag([1.0, -1.0]).astype(np.complex128))
    assert to_qutip(h).isoper

    op = Operator(destroy(2).full())
    assert to_qutip(op).isoper

    rho = DensityOperator(np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.complex128))
    assert to_qutip(rho).isoper


def test_to_qutip_rejects_unsupported_type():
    with pytest.raises(TypeError, match="State, Operator, Hamiltonian, or DensityOperator"):
        to_qutip(np.eye(2))  # type: ignore[arg-type]


def test_round_trip_state():
    original = basis(2, 1)
    back = to_qutip(from_qutip(original))
    assert np.allclose(back.full(), original.full())
    assert back.dims == original.dims


def test_round_trip_hamiltonian_operator_and_density():
    h = from_qutip(sigmaz())
    assert np.allclose(to_qutip(h).full(), sigmaz().full())

    op = from_qutip(destroy(2))
    assert np.allclose(to_qutip(op).full(), destroy(2).full())

    state = State(np.array([0.0, 1.0], dtype=np.complex128), 1)
    assert np.allclose(from_qutip(to_qutip(state)).state, state.state)

    rho_q = basis(2, 0) * basis(2, 0).dag()
    rho = from_qutip(rho_q)
    assert isinstance(rho, DensityOperator)
    assert np.allclose(to_qutip(rho).full(), rho_q.full())
