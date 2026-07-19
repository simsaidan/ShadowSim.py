import numpy as np


def tensor(lst):
    """Return the tensor product of the arrays in ``lst``."""
    result = lst[0]
    for i in range(1, len(lst)):
        result = np.kron(result, lst[i])
    return result
