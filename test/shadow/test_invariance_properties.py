"""Property catalog: ``check_invariance`` / IP closure.

Invariants exercised by Hypothesis tests in this module:

* Sparse and dense paths agree on closure reports (n ≤ 3).
* Closure is monotonic: ``original ⊆ closure``, ``growth = |closure| - |original|``.
* Closure is idempotent: closing an already-closed set adds nothing.
"""
