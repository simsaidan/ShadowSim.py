import numpy as np
import pytest

from shadowsim.core import LocalOperator, Operator


def test_local_operator_requires_square_matrix():
    with pytest.raises(ValueError, match=r"square 2D array; got shape \(1, 3\)"):
        LocalOperator(np.array([[1.0, 0.0, 0.0]]), sites=[0], local_dim=2)
    with pytest.raises(TypeError, match="numpy array"):
        LocalOperator([[1.0, 0.0], [0.0, 1.0]], sites=[0], local_dim=2)  # type: ignore[arg-type]


def test_local_operator_requires_contiguous_unique_integer_sites():
    mat = np.eye(4)
    with pytest.raises(ValueError, match=r"all sites must be unique; got \[0, 0\]"):
        LocalOperator(mat, sites=[0, 0], local_dim=2)
    with pytest.raises(TypeError, match=r"all sites must be integers; got \[0, '1'\]"):
        LocalOperator(mat, sites=[0, "1"], local_dim=2)
    with pytest.raises(ValueError, match=r"contiguous range of integers; got \[0, 2\]"):
        LocalOperator(mat, sites=[0, 2], local_dim=2)
    with pytest.raises(ValueError, match=r"at least one site; got \[\]"):
        LocalOperator(np.eye(2), sites=[], local_dim=2)
    with pytest.raises(TypeError, match="sites must be a list"):
        LocalOperator(np.eye(2), sites=(0,), local_dim=2)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="local_dim must be an integer"):
        LocalOperator(np.eye(2), sites=[0], local_dim=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="local_dim must be a positive integer"):
        LocalOperator(np.eye(2), sites=[0], local_dim=0)


def test_local_operator_rejects_dimension_mismatch():
    mat = np.eye(4)
    with pytest.raises(ValueError, match="invalid number of sites"):
        LocalOperator(mat, sites=[0], local_dim=2)


def test_local_operator_to_full_operator_adds_identity_padding():
    local = LocalOperator(np.eye(4), sites=[1, 2], local_dim=2)
    full = local.to_full_operator(total_sites=4)
    expected = np.kron(np.eye(2), np.kron(np.eye(4), np.eye(2)))
    assert isinstance(full, Operator)
    assert full.matrix.shape == (16, 16)
    assert np.allclose(full.matrix, expected)


def test_local_operator_to_full_operator_handles_high_index_block():
    local = LocalOperator(np.eye(8), sites=[3, 4, 5], local_dim=2)
    full = local.to_full_operator(total_sites=6)
    expected = np.kron(np.eye(8), np.eye(8))
    assert np.allclose(full.matrix, expected)


def test_local_operator_to_full_operator_validates_total_sites():
    local = LocalOperator(np.eye(4), sites=[1, 2], local_dim=2)
    with pytest.raises(TypeError, match="total_sites must be an integer"):
        local.to_full_operator(4.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="total_sites must be positive"):
        local.to_full_operator(0)
    with pytest.raises(ValueError, match="too small"):
        local.to_full_operator(2)
    negative = LocalOperator(np.eye(2), sites=[-1], local_dim=2)
    with pytest.raises(ValueError, match=r"non-negative; got \[-1\]"):
        negative.to_full_operator(2)


def test_local_operator_accessors_and_conversions():
    local = LocalOperator(np.eye(2), sites=[0], local_dim=2)
    assert local.get_sites() == [0]
    assert local.get_local_dim() == 2
    assert np.allclose(local.get_matrix(), np.eye(2))
    as_op = local.to_operator()
    assert isinstance(as_op, Operator)
    assert as_op == Operator(np.eye(2))


def test_local_operator_str_and_repr():
    local = LocalOperator(np.eye(2), sites=[0], local_dim=2)
    text = str(local)
    rep = repr(local)
    assert "LocalOperator(" in text
    assert "sites=[0]" in text
    assert "LocalOperator(" in rep
    assert "local_dim=2" in rep
