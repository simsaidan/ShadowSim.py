import numpy as np
from typing import Literal

##CONSTANTS

zero_state_two_qubits = np.array([1, 0, 0, 0])
one_state_two_qubits = np.array([0, 1, 0, 0])
two_state_two_qubits = np.array([0, 0, 1, 0])
three_state_two_qubits = np.array([0, 0, 0, 1])

I = np.eye(2)


# FUNCTIONS
def unitary(U):
    """Returns whether a numpy matrix U is unitary.

    Parameter U: The matrix to check if it is unitary.
    Precondition: U is a numpy matrix.
    """
    return np.allclose(np.eye(U.shape[0]), np.dot(U, U.conjugate().T))


def hermitian(H):
    """Returns whether a numpy matrix H is Hermitian.

    Parameter H: The matrix to check if it is Hermitian.
    Precondition: H is a numpy matrix.
    """
    return np.allclose(H, H.conjugate().T)


def _real_parts_of_eigenvalues(matrix):
    eigvals = np.linalg.eigvals(matrix)
    return np.real_if_close(eigvals, tol=1000).real


def positive_semidefinite(matrix):
    """Returns whether a matrix is positive semidefinite."""
    return np.all(_real_parts_of_eigenvalues(matrix) >= 0)


def positive_definite(matrix):
    """Returns whether a matrix is positive definite."""
    return np.all(_real_parts_of_eigenvalues(matrix) > 0)


def negative_semidefinite(matrix):
    """Returns whether a matrix is negative semidefinite."""
    return np.all(_real_parts_of_eigenvalues(matrix) <= 0)


def negative_definite(matrix):
    """Returns whether a matrix is negative definite."""
    return np.all(_real_parts_of_eigenvalues(matrix) < 0)


def indefinite(matrix):
    """Returns whether a matrix has both positive and negative eigenvalues."""
    eigvals = _real_parts_of_eigenvalues(matrix)
    return np.any(eigvals > 0) and np.any(eigvals < 0)


def flip_dict(d):
    """
    Given a dictionary d with a string key, it returns a new dictionary with
    the key reversed and the value the same. Used for switching the endianness
    of the measurements.

    Parameter d: The dictionary to flip.
    Precondition: d is a dictionary with string keys.
    """
    return {k[::-1]: v for k, v in d.items()}


def tensor(lst):
    """
    Returns the tensor product of the arrays in lst.

    Parameter lst: The list of arrays to tensor product.
    Precondition: lst contains only Numpy arrays.
    """
    result = lst[0]
    for i in range(1, len(lst)):
        result = np.kron(result, lst[i])
    return result


def next_power_of_two(n):
    """
    Finds the first number >= n that is also a power of 2. For example,
    next_power_of_two(5) returns 8 and next_power_of_two(8) returns 8.

    Parameter n: The number to find the next power of 2 for.
    Precondition: n is a non-negative integer.
    """
    assert isinstance(n, int), "n must be an integer"
    assert n >= 0, "n must be non-negative"

    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()
