import numpy as np

from shadowsim.utils.indefinite import indefinite


def test_indefinite_true_for_mixed_sign_spectrum():
    assert indefinite(np.diag([-2.0, 0.0, 3.0]))


def test_indefinite_false_for_semidefinite_matrices():
    assert not indefinite(np.diag([0.0, 1.0, 2.0]))
    assert not indefinite(np.diag([-2.0, -1.0, 0.0]))
