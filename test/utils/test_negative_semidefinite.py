import numpy as np

from shadowsim.utils.definiteness import negative_semidefinite


def test_negative_semidefinite_true_cases():
    assert negative_semidefinite(-np.eye(3))
    assert negative_semidefinite(np.diag([-4.0, -1.0, 0.0]))


def test_negative_semidefinite_treats_tiny_positive_eigenvalue_as_zero():
    assert negative_semidefinite(np.diag([1e-12, -1.0]))
    assert not negative_semidefinite(np.diag([-1e-9, 1e-9]))


def test_negative_semidefinite_false_for_indefinite_matrix():
    assert not negative_semidefinite(np.diag([-1.0, 2.0]))


def test_negative_semidefinite_false_for_non_hermitian_matrix():
    # Eigenvalues are -1 and -1, while v† B v is positive for v = [1, 1].
    matrix = np.array([[-1.0, 100.0], [0.0, -1.0]])
    assert not negative_semidefinite(matrix)
