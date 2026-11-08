import numpy as np

from shadowsim.utils.definiteness import positive_semidefinite


def test_positive_semidefinite_true_cases():
    assert positive_semidefinite(np.eye(3))
    assert positive_semidefinite(np.diag([0.0, 1.0, 4.0]))


def test_positive_semidefinite_treats_tiny_negative_eigenvalue_as_zero():
    assert positive_semidefinite(np.diag([-1e-12, 1.0]))
    assert not positive_semidefinite(np.diag([-1e-9, 1e-9]))


def test_positive_semidefinite_false_for_indefinite_matrix():
    assert not positive_semidefinite(np.diag([-1.0, 2.0]))


def test_positive_semidefinite_false_for_non_hermitian_matrix():
    # Eigenvalues are 1 and 1, while v† A v is negative for v = [1, -0.1].
    matrix = np.array([[1.0, 100.0], [0.0, 1.0]])
    assert not positive_semidefinite(matrix)
