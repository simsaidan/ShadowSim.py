"""Shared pytest configuration for ShadowSim.

Registers Hypothesis settings profiles:

* ``default`` — moderate ``max_examples`` and a finite per-example deadline for
  local runs. Failures print a ``@reproduce_failure`` blob (and Hypothesis
  records the case in the local example database under ``.hypothesis/``).
* ``ci`` — derandomized generation so CI is deterministic, ``print_blob`` so
  failing seeds/blobs appear in logs, and no local database / deadline (shared
  runners are slow and ephemeral).

Select a profile with ``HYPOTHESIS_PROFILE``, ``pytest --hypothesis-profile``,
or automatically via the ``CI`` environment variable (set by GitHub Actions).

Qulacs vendors ``libgomp``. On Linux that library needs static TLS, and the
reserve is gone once NumPy, SciPy, and QuTiP have been imported
(``cannot allocate memory in static TLS block``). Load Qulacs before those
test modules when the extra is installed.
"""

import importlib.util
import os

# Execute the import here, before collection imports the scientific stack.
if importlib.util.find_spec("qulacs") is not None:
    import qulacs  # noqa: F401

from hypothesis import settings

settings.register_profile(
    "default",
    max_examples=100,
    deadline=200,
    print_blob=True,
)

settings.register_profile(
    "ci",
    max_examples=100,
    derandomize=True,
    deadline=None,
    database=None,
    print_blob=True,
)

_profile = os.getenv("HYPOTHESIS_PROFILE")
if _profile:
    settings.load_profile(_profile)
elif os.getenv("CI"):
    settings.load_profile("ci")
else:
    settings.load_profile("default")
