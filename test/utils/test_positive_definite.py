import numpy as np

from shadowsim.utils.positive_definite import positive_definite


def test_positive_definite_true_cases():
    assert positive_definite(np.eye(3))
    assert positive_definite(np.diag([0.5, 1.0, 4.0]))


def test_positive_definite_false_with_zero_or_negative_eigenvalue():
    assert not positive_definite(np.diag([0.0, 1.0, 2.0]))
    assert not positive_definite(np.diag([-1.0, 2.0]))
