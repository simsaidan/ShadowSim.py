import numpy as np
import pytest

from shadowsim.core import DensityOperator, State

RHO0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.complex128)
MIXED = np.diag([0.5, 0.5]).astype(np.complex128)


def test_density_operator_valid_and_trace():
    rho = DensityOperator(RHO0)
    assert np.allclose(rho.matrix, RHO0)
    assert np.isclose(rho.trace(), 1.0)
    assert "DensityOperator(matrix=" in str(rho)
    assert "DensityOperator(matrix=" in repr(rho)


def test_density_operator_equality():
    a = DensityOperator(RHO0)
    b = DensityOperator(RHO0.copy())
    c = DensityOperator(MIXED)
    assert a == b
    assert a != c


def test_density_operator_from_state():
    psi = State(np.array([0.0, 1.0], dtype=np.complex128), 1)
    rho = DensityOperator.from_state(psi)
    assert np.allclose(rho.matrix, [[0.0, 0.0], [0.0, 1.0]])


def test_density_operator_rejects_bad_inputs():
    with pytest.raises(TypeError, match="numpy array"):
        DensityOperator([[1.0, 0.0], [0.0, 0.0]])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="square"):
        DensityOperator(np.ones((2, 3), dtype=np.complex128))
    with pytest.raises(ValueError, match="Hermitian"):
        DensityOperator(np.array([[0.0, 1.0], [0.0, 0.0]], dtype=np.complex128))
    with pytest.raises(ValueError, match="positive semidefinite"):
        DensityOperator(np.diag([1.5, -0.5]).astype(np.complex128))
    with pytest.raises(ValueError, match="trace 1"):
        DensityOperator(np.eye(2, dtype=np.complex128))
    with pytest.raises(TypeError, match="State"):
        DensityOperator.from_state(np.array([1.0, 0.0]))  # type: ignore[arg-type]
