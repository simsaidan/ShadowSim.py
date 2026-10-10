"""Property catalog: ``State`` validation.

Invariants exercised by Hypothesis tests in this module:

* Random normalized vectors of length ``local_dim**n`` are accepted.
* Incorrect length or non-unit norm is rejected.
"""
