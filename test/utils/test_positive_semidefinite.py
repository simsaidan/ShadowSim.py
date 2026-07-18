import numpy as np

from src.utils.positive_semidefinite import positive_semidefinite


def test_positive_semidefinite_true_cases():
    assert positive_semidefinite(np.eye(3))
    assert positive_semidefinite(np.diag([0.0, 1.0, 4.0]))


def test_positive_semidefinite_false_for_indefinite_matrix():
    assert not positive_semidefinite(np.diag([-1.0, 2.0]))
