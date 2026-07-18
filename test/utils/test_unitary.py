import numpy as np

from src.utils.unitary import unitary


_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_HAD = np.array([[1.0, 1.0], [1.0, -1.0]], dtype=np.complex128) / np.sqrt(2)


def test_unitary_identity_and_paulis():
    assert unitary(np.eye(2))
    assert unitary(np.eye(3))
    assert unitary(_X)
    assert unitary(_Y)
    assert unitary(_Z)


def test_unitary_hadamard_phase():
    assert unitary(_HAD)
    assert unitary(np.diag(np.exp([0.5j, -0.5j])))


def test_unitary_random_via_qr():
    rng = np.random.default_rng(0)
    q, _ = np.linalg.qr(rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4)))
    assert unitary(q)


def test_unitary_false_for_non_unitary():
    assert not unitary(np.array([[1.0, 2.0], [0.0, 1.0]]))
    assert not unitary(np.array([[1.0, 0.0], [1.0, 0.0]]))
