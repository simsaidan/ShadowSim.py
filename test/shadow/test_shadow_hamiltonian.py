import numpy as np

from shadowsim.core import Hamiltonian
from shadowsim.core import Operator
from shadowsim.core import OperatorSet
from shadowsim.shadow import ShadowHamiltonian


X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)


def test_shadow_hamiltonian_is_quiet_by_default(capsys):
    ShadowHamiltonian(OperatorSet([Operator(Z)]), Hamiltonian(X))

    assert capsys.readouterr().out == ""


def test_shadow_hamiltonian_reports_progress_when_verbose(capsys):
    ShadowHamiltonian(
        OperatorSet([Operator(Z)]),
        Hamiltonian(X),
        verbose=True,
    )

    output = capsys.readouterr().out
    assert "Pauli counts ->" in output
    assert "Operator closure size:" in output
