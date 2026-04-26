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
    """Returns whether a numpy matrix is unitary"""
    return np.allclose(np.eye(U.shape[0]), np.dot(U, U.conjugate().T))


def flip_dict(d):
    """
    Given a dictionary d with a string key, it returns
    a new dictionary with the key reversed and the value the same.

    Used for switching the endianness of the measurements.
    """
    res = {}
    for k, v in d.items():
        res[k[::-1]] = v
    return res


def tensor(lst):
    """
    Returns the tensor product of the arrays in lst.

    Preconditions:
    - lst contains only Numpy arrays
    """
    result = lst[0]
    for i in range(1, len(lst)):
        result = np.kron(result, lst[i])
    return result


def next_power_of_two(n):
    """Finds the first number >= n that is also a
    power of 2.

    Used for figuring out the size and padding of the JMatrix."""
    power = 1
    while power < n:
        power <<= 1
    return power
