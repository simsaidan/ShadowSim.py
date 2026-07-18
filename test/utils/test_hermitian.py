import numpy as np

from src.utils.hermitian import hermitian


_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)


def test_hermitian_identity_paulis_real_symmetric():
    assert hermitian(np.eye(2))
    assert hermitian(_X)
    assert hermitian(_Z)


def test_hermitian_pauli_y():
    assert hermitian(_Y)


def test_hermitian_general_complex():
    rng = np.random.default_rng(1)
    a = rng.standard_normal((3, 3)) + 1j * rng.standard_normal((3, 3))
    h = a + a.conjugate().T
    assert hermitian(h)


def test_hermitian_false_for_non_hermitian():
    assert not hermitian(np.array([[1.0 + 2j, 0.0], [0.0, 0.0]]))
    assert not hermitian(np.array([[0.0, 1.0], [2.0, 0.0]]))
