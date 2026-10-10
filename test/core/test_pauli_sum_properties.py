"""Property catalog: ``PauliSum`` linear combinations.

Invariants exercised by Hypothesis tests in this module:

* ``(A + B).to_matrix()`` equals ``A.to_matrix() + B.to_matrix()`` (n ≤ 4).
* Real coefficients imply a Hermitian matrix and ``is_hermitian()`` is true.
* Parse / construct round-trips preserve merged terms for generated expressions.
"""
