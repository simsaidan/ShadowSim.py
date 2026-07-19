import numpy as np

from shadowsim.utils.negative_definite import negative_definite


def test_negative_definite_true_cases():
    assert negative_definite(-np.eye(3))
    assert negative_definite(np.diag([-4.0, -1.0, -0.5]))


def test_negative_definite_false_with_zero_or_positive_eigenvalue():
    assert not negative_definite(np.diag([-2.0, -1.0, 0.0]))
    assert not negative_definite(np.diag([-1.0, 2.0]))
