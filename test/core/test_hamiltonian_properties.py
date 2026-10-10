"""Property catalog: ``Hamiltonian`` / ``LocalHamiltonian``.

Invariants exercised by Hypothesis tests in this module:

* Non-Hermitian inputs are rejected; real-coefficient PauliSums are accepted.
* Accepted Hamiltonians have Hermitian matrices.
* Local embedding equals identity-padded tensor product and preserves Hermiticity.
"""
