"""Property catalog: matrix utility predicates and Kronecker products.

Invariants exercised by Hypothesis tests in this module:

* ``hermitian(H)`` iff ``H == H.conj().T`` on small random matrices.
* ``unitary(U)`` iff ``U @ U.conj().T == I`` on small random unitaries.
* ``tensor(factors)`` equals a chained ``np.kron`` of the same factors.
"""
