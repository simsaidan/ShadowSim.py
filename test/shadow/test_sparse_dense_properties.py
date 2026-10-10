"""Property catalog: sparse vs dense shadow agreement.

Invariants exercised by Hypothesis tests in this module:

* ``assert_core_agreement`` holds for random Pauli Hamiltonians / observables.
* ``assert_shadow_agreement`` holds for the same models (n ≤ 4; dense path capped).
* Path flags differ (``used_sparse_pauli_path``) while numerical outputs match.
"""
