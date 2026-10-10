"""Seeded Pauli-model generators shared by regression and property tests."""

from __future__ import annotations

import numpy as np

from shadowsim.core import PauliString, PauliSum

ATOL = 1e-8
RTOL = 1e-7
_LETTERS = ("I", "X", "Y", "Z")


def _identity_label(n: int) -> str:
    return "I" * n


def _commutes(a: str, b: str) -> bool:
    coeff, _ = PauliString.from_string(a).commutator(PauliString.from_string(b))
    return coeff is None


def random_pauli_label(
    rng: np.random.Generator,
    n: int,
    *,
    allow_identity: bool = False,
) -> str:
    """Sample a length-``n`` Pauli word."""
    while True:
        label = "".join(str(rng.choice(_LETTERS)) for _ in range(n))
        if allow_identity or label != _identity_label(n):
            return label


def _sample_coeff(rng: np.random.Generator, scale: float) -> float:
    """Sample a nonzero real coefficient in ``[-scale, scale]``."""
    for _ in range(64):
        c = float(rng.uniform(-scale, scale))
        if abs(c) > 1e-12 * max(scale, 1.0):
            return c
    return float(scale)


def random_pauli_sum(
    rng: np.random.Generator,
    n: int,
    n_terms: int,
    scale: float,
    *,
    commuting: bool | None = None,
) -> PauliSum:
    """Build a seeded real-coefficient PauliSum with the requested structure."""
    max_terms = max(1, 4**n - 1)
    n_terms = max(1, min(int(n_terms), max_terms))
    if commuting is False:
        n_terms = max(2, n_terms)

    for _attempt in range(256):
        labels: list[str] = []
        if commuting is True:
            pool = [
                "".join(_LETTERS[i] for i in idxs)
                for idxs in np.ndindex(*([4] * n))
                if "".join(_LETTERS[i] for i in idxs) != _identity_label(n)
            ]
            rng.shuffle(pool)
            for lab in pool:
                if all(_commutes(lab, prev) for prev in labels):
                    labels.append(lab)
                if len(labels) >= n_terms:
                    break
            if not labels:
                labels = [random_pauli_label(rng, n)]
        else:
            seen: set[str] = set()
            while len(labels) < n_terms:
                lab = random_pauli_label(rng, n)
                if lab not in seen:
                    seen.add(lab)
                    labels.append(lab)

        if commuting is False:
            has_noncommuting = any(
                not _commutes(labels[i], labels[j]) for i in range(len(labels)) for j in range(i + 1, len(labels))
            )
            if not has_noncommuting:
                continue

        terms = {lab: _sample_coeff(rng, scale) for lab in labels}
        return PauliSum(terms)

    raise RuntimeError("failed to sample PauliSum with requested constraints")


def observable_labels(rng: np.random.Generator, n: int, k: int) -> list[str]:
    """Sample ``k`` distinct non-identity Pauli words."""
    k = max(1, min(int(k), 4**n - 1))
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < k:
        lab = random_pauli_label(rng, n)
        if lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out
