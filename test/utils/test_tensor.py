import numpy as np
import pytest

from src.utils.tensor import tensor


_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_HAD = np.array([[1.0, 1.0], [1.0, -1.0]], dtype=np.complex128) / np.sqrt(2)


@pytest.mark.parametrize(
    "matrices, expected_shape",
    [
        ([_X], (2, 2)),
        ([_X, _Y], (4, 4)),
        ([_Z, _HAD, np.eye(2)], (8, 8)),
    ],
)
def test_tensor_shape_and_matches_kron_chain(matrices, expected_shape):
    out = tensor(matrices)
    assert out.shape == expected_shape
    ref = matrices[0]
    for matrix in matrices[1:]:
        ref = np.kron(ref, matrix)
    assert np.allclose(out, ref)


def test_tensor_two_qubits_pauli_product():
    out = tensor([_Z, _X])
    assert np.allclose(out, np.kron(_Z, _X))


def test_tensor_three_single_qubits():
    a, b = np.array([1.0, 2.0]), np.array([-1j, 1.0])
    c = np.array([3.0, 4.0])
    out = tensor([a, b, c])
    assert np.allclose(out, np.kron(np.kron(a, b), c))
