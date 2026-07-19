import numpy as np


def hermitian(H):
    """Return whether the NumPy matrix ``H`` is Hermitian."""
    return np.allclose(H, H.conjugate().T)
