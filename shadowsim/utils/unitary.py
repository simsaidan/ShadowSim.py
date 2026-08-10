"""Unitary-matrix checks."""

import numpy as np


def unitary(U):
    """Return whether the NumPy matrix ``U`` is unitary."""
    return np.allclose(np.eye(U.shape[0]), np.dot(U, U.conjugate().T))
