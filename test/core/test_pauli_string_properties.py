"""Property catalog: ``PauliString`` algebra.

Invariants exercised by Hypothesis tests in this module:

* ``matrix()`` equals the Kronecker product of single-qubit Paulis in string order.
* ``multiply`` / ``commutator`` agree with dense matrix arithmetic (n ≤ 4).
* Commutator vanishes iff an even number of qubit positions anticommute.
"""
