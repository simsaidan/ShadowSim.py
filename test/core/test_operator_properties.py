"""Property catalog: ``Operator`` dual representations.

Invariants exercised by Hypothesis tests in this module:

* Pauli-backed and densified constructors agree on ``matrix`` (n ≤ 4).
* Hermitian / unitary / definiteness flags match ``shadowsim.utils`` predicates.
* Equality is consistent with numerical matrix agreement.
"""
