import numpy as np
import pytest

import shadowsim.shadow.shadow_hamiltonian as module
from shadowsim.core import Hamiltonian, LocalHamiltonian, Operator, OperatorSet
from shadowsim.core.pauli_sum import PauliSum
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


def test_one_qubit_known_pauli_closure_and_h_s():
    """H = X, operator_set = {Z}: closure is {Y, Z} with a known H_S."""
    shadow = ShadowHamiltonian(OperatorSet([Operator(Z)]), Hamiltonian(X))

    assert shadow.pauli_set == {"X"}
    assert shadow.operator_pauli_set == {"Z"}
    assert shadow.operator_pauli_closure == {"Y", "Z"}
    assert shadow.basis == ["Y", "Z"]
    assert shadow.num_qubits == 1

    assert len(shadow.pauli_decomposition) == 1
    assert shadow.pauli_decomposition["X"] == pytest.approx(1 + 0j)

    expected_h_s = np.array([[0, -2j], [2j, 0]], dtype=np.complex128)
    assert np.allclose(shadow.H_S, expected_h_s)
    assert np.allclose(shadow.shadow, expected_h_s)
    assert np.allclose(shadow.get_H_S(), expected_h_s)
    assert shadow.is_hermitian()
    assert not shadow.is_unitary()


def test_three_qubit_already_closed_pauli_set_has_nonzero_h_s():
    """XII+IIX with {XII, YII, ZII, IIX} stays size-4 and has nonzero H_S."""
    hamiltonians = [Hamiltonian("XII"), Hamiltonian("IIX")]
    observables = OperatorSet(["XII", "YII", "ZII", "IIX"])

    shadow = ShadowHamiltonian(observables, hamiltonians)

    expected = {"XII", "YII", "ZII", "IIX"}
    assert shadow.used_sparse_pauli_path is True
    assert shadow.operator_pauli_set == expected
    assert shadow.operator_pauli_closure == expected
    assert shadow.basis == sorted(expected)
    assert shadow.H_S.shape == (4, 4)
    assert shadow.num_qubits == 3
    assert float(np.max(np.abs(shadow.H_S))) > 0.0


def test_local_hamiltonian_requires_explicit_num_qubits():
    with pytest.raises(ValueError, match="pass num_qubits="):
        ShadowHamiltonian(
            OperatorSet([Operator(Z)]),
            [LocalHamiltonian(X, [0])],
        )

    shadow = ShadowHamiltonian(
        OperatorSet([Operator(Z)]),
        [LocalHamiltonian(X, [0])],
        num_qubits=1,
    )
    assert shadow.used_sparse_pauli_path is False
    assert shadow.basis == ["Y", "Z"]
    assert np.allclose(
        shadow.H_S,
        np.array([[0, -2j], [2j, 0]], dtype=np.complex128),
    )


def test_sparse_and_dense_paths_agree_one_and_three_qubits():
    dense_1q = ShadowHamiltonian(OperatorSet([Operator(Z)]), Hamiltonian(X))
    sparse_1q = ShadowHamiltonian(OperatorSet(["Z"]), Hamiltonian("X"))
    assert dense_1q.used_sparse_pauli_path is False
    assert sparse_1q.used_sparse_pauli_path is True
    assert sparse_1q.basis == dense_1q.basis
    assert np.allclose(sparse_1q.H_S, dense_1q.H_S)

    h_labels = [Hamiltonian("XII"), Hamiltonian("IIX")]
    op_labels = OperatorSet(["XII", "YII", "ZII", "IIX"])
    sparse_3q = ShadowHamiltonian(op_labels, h_labels)
    dense_3q = ShadowHamiltonian(
        OperatorSet([Operator(op.matrix) for op in op_labels.operators]),
        [Hamiltonian(h.matrix) for h in h_labels],
    )
    assert sparse_3q.used_sparse_pauli_path is True
    assert dense_3q.used_sparse_pauli_path is False
    assert sparse_3q.basis == dense_3q.basis
    assert sparse_3q.operator_pauli_closure == dense_3q.operator_pauli_closure
    assert np.allclose(sparse_3q.H_S, dense_3q.H_S)


def test_sparse_and_dense_paths_agree_two_qubit_nontrivial_closure():
    """H = XI, observables = {ZI}: closure adds YI."""
    sparse = ShadowHamiltonian(OperatorSet(["ZI"]), Hamiltonian("XI"))
    dense = ShadowHamiltonian(
        OperatorSet([Operator(sparse.operator_set.operators[0].matrix)]),
        Hamiltonian(sparse.H.matrix),
    )
    assert sparse.used_sparse_pauli_path is True
    assert dense.used_sparse_pauli_path is False
    assert sparse.operator_pauli_closure == {"YI", "ZI"}
    assert sparse.basis == dense.basis == ["YI", "ZI"]
    assert np.allclose(sparse.H_S, dense.H_S)
    expected = np.array([[0, -2j], [2j, 0]], dtype=np.complex128)
    assert np.allclose(sparse.H_S, expected)


def test_sparse_path_skips_dense_pauli_scan(monkeypatch):
    def _fail_dense(*_args, **_kwargs):
        raise AssertionError("dense Pauli tomography should not run on the sparse path")

    monkeypatch.setattr(module, "_dense_pauli_decomposition", _fail_dense)
    monkeypatch.setattr(
        module,
        "combined_hamiltonian_matrix",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("combined_hamiltonian_matrix should not run on the sparse path")
        ),
    )

    shadow = ShadowHamiltonian(OperatorSet(["Z"]), Hamiltonian("X"))
    assert shadow.used_sparse_pauli_path is True
    assert np.allclose(
        shadow.H_S,
        np.array([[0, -2j], [2j, 0]], dtype=np.complex128),
    )


def test_sparse_path_str_repr_do_not_densify():
    shadow = ShadowHamiltonian(OperatorSet(["Z"]), Hamiltonian("X"))
    assert shadow.H._matrix_cache is None
    text = str(shadow)
    rep = repr(shadow)
    assert shadow.H._matrix_cache is None
    assert "pauli_terms=1" in text
    assert "n_qubits=1" in text
    assert "sparse=True" in rep
    assert "basis_size=2" in rep


def test_shadow_hamiltonian_rejects_empty_hamiltonian_sequence():
    with pytest.raises(ValueError, match="non-empty sequence"):
        ShadowHamiltonian(OperatorSet([Operator(Z)]), [])


def test_shadow_hamiltonian_rejects_operator_shape_mismatch():
    with pytest.raises(ValueError, match="same matrix shape as H"):
        ShadowHamiltonian(
            OperatorSet([Operator(np.eye(4, dtype=np.complex128))]),
            Hamiltonian(X),
        )


def test_sparse_path_rejects_num_qubits_and_operator_mismatch():
    with pytest.raises(ValueError, match="does not match Pauli word length"):
        ShadowHamiltonian(OperatorSet(["Z"]), Hamiltonian("X"), num_qubits=2)
    with pytest.raises(ValueError, match="same matrix shape as H"):
        ShadowHamiltonian(OperatorSet(["ZZ"]), Hamiltonian("X"))


def test_sparse_helpers_reject_missing_pauli_and_skip_out_of_basis():
    with pytest.raises(ValueError, match="expected Pauli-backed Hamiltonian"):
        module._merge_pauli_hamiltonians([Hamiltonian(X)])
    with pytest.raises(ValueError, match="expected Pauli-backed Hamiltonian"):
        module._merge_pauli_hamiltonians([Hamiltonian("X"), Hamiltonian(X)])
    with pytest.raises(ValueError, match="expected Pauli-backed operators"):
        module._operator_pauli_labels(OperatorSet([Operator(Z)]), tol=1e-10)

    tiny = OperatorSet([Operator(PauliSum({"X": 1e-20, "Z": 1.0}))])
    assert module._operator_pauli_labels(tiny, tol=1e-10) == {"Z"}

    # [Z, X] = 2i Y is outside basis {X}, so the out-of-basis branch is skipped.
    h_s = module._assemble_h_s(["X"], {"Z": 1.0})
    assert h_s.shape == (1, 1)
    assert h_s[0, 0] == 0.0


def test_shadow_hamiltonian_str_and_repr():
    shadow = ShadowHamiltonian(OperatorSet([Operator(Z)]), Hamiltonian(X))

    text = str(shadow)
    rep = repr(shadow)
    assert "ShadowHamiltonian(" in text
    assert "n_qubits=1" in text
    assert "shadow.shape=(2, 2)" in text
    assert "basis_size=2" in rep
    assert "tol=1e-10" in rep


def test_shadow_hamiltonian_rejects_non_power_of_two_infer_dim():
    bad = Hamiltonian(np.diag([1.0, 2.0, 3.0]).astype(np.complex128))
    with pytest.raises(ValueError, match="power of 2"):
        ShadowHamiltonian(OperatorSet([Operator(bad.matrix)]), bad)


def test_shadow_hamiltonian_rejects_mismatched_full_domain_sizes():
    with pytest.raises(ValueError, match="same matrix size"):
        ShadowHamiltonian(
            OperatorSet([Operator(X)]),
            [Hamiltonian(X), Hamiltonian(np.eye(4, dtype=np.complex128))],
        )


def test_shadow_hamiltonian_rejects_non_power_of_two_when_num_qubits_forced():
    bad = Hamiltonian(np.diag([1.0, 2.0, 3.0]).astype(np.complex128))
    with pytest.raises(ValueError, match="power of 2 to use a Pauli-string basis"):
        ShadowHamiltonian(
            OperatorSet([Operator(bad.matrix)]),
            bad,
            num_qubits=2,
        )


def test_shadow_hamiltonian_rejects_non_square_combined_matrix(monkeypatch):
    monkeypatch.setattr(
        module,
        "combined_hamiltonian_matrix",
        lambda terms, nq: np.zeros((2, 3), dtype=np.complex128),
    )

    class FakeHamiltonian:
        def __init__(self, matrix):
            self.matrix = matrix

    monkeypatch.setattr(module, "Hamiltonian", FakeHamiltonian)
    # Pass a sequence so isinstance(..., Hamiltonian) does not use the fake class.
    with pytest.raises(ValueError, match="square matrix"):
        ShadowHamiltonian(
            OperatorSet([Operator(Z)]),
            [Hamiltonian(X)],
            num_qubits=1,
        )
