"""Property catalog: ``Pauli`` algebra.

Invariants exercised by Hypothesis tests in this module:

* Multiplication is associative up to phase × label.
* ``multiply`` agrees with dense matrix products (``phase * R.matrix()``).
* ``commutator`` matches ``P @ Q - Q @ P``; ``(None, None)`` iff matrices commute.
* Every Pauli matrix is Hermitian.
"""
