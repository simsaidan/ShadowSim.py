"""Seeded Pauli-model generators shared by regression and property tests."""

import numpy as np
from hypothesis import strategies as st

from shadowsim.core import Hamiltonian, OperatorSet, Pauli, PauliString, PauliSum

ATOL = 1e-8
RTOL = 1e-7
_LETTERS = ("I", "X", "Y", "Z")
MAX_PROPERTY_QUBITS = 4
MAX_SHADOW_PROPERTY_QUBITS = 3


@st.composite
def pauli_labels(draw: st.DrawFn) -> str:
    """Draw a single-qubit Pauli label in ``{I,X,Y,Z}``."""
    return draw(st.sampled_from(_LETTERS))


@st.composite
def pauli_words(draw: st.DrawFn, *, min_n: int = 1, max_n: int = MAX_PROPERTY_QUBITS) -> str:
    """Draw a length-``n`` Pauli word with ``n`` in ``[min_n, max_n]``."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    return "".join(draw(st.sampled_from(_LETTERS)) for _ in range(n))


@st.composite
def paulis(draw: st.DrawFn) -> Pauli:
    """Draw a :class:`~shadowsim.core.Pauli`."""
    return Pauli(draw(pauli_labels()))


@st.composite
def pauli_strings(draw: st.DrawFn, *, min_n: int = 1, max_n: int = MAX_PROPERTY_QUBITS) -> PauliString:
    """Draw a :class:`~shadowsim.core.PauliString`."""
    return PauliString.from_string(draw(pauli_words(min_n=min_n, max_n=max_n)))


@st.composite
def real_pauli_sums(
    draw: st.DrawFn,
    *,
    min_n: int = 1,
    max_n: int = MAX_PROPERTY_QUBITS,
    min_terms: int = 1,
    max_terms: int = 4,
) -> PauliSum:
    """Draw a real-coefficient :class:`~shadowsim.core.PauliSum` (nonzero)."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    n_terms = draw(st.integers(min_value=min_terms, max_value=min(max_terms, max(1, 4**n - 1))))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    scale = draw(st.floats(min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False))
    return random_pauli_sum(np.random.default_rng(seed), n, n_terms, scale)


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


def normalize_state_vector(vec: np.ndarray) -> np.ndarray:
    """Return ``vec / ||vec||`` as complex128 (raises if near-zero)."""
    arr = np.asarray(vec, dtype=np.complex128).reshape(-1)
    norm = np.linalg.norm(arr)
    if norm <= 1e-15:
        raise ValueError("cannot normalize a near-zero vector")
    return arr / norm


@st.composite
def normalized_states(
    draw: st.DrawFn,
    *,
    min_n: int = 1,
    max_n: int = MAX_PROPERTY_QUBITS,
    local_dim: int = 2,
) -> tuple[np.ndarray, int, int]:
    """Draw ``(normalized_vector, num_qubits, local_dim)``."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    dim = local_dim**n
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(dim) + 1j * rng.standard_normal(dim)
    return normalize_state_vector(raw), n, local_dim


@st.composite
def hermitian_matrices(
    draw: st.DrawFn,
    *,
    min_dim: int = 1,
    max_dim: int = 8,
) -> np.ndarray:
    """Draw a small random Hermitian matrix."""
    dim = draw(st.integers(min_value=min_dim, max_value=max_dim))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((dim, dim)) + 1j * rng.standard_normal((dim, dim))
    return a + a.conjugate().T


@st.composite
def sparse_pauli_models(
    draw: st.DrawFn,
    *,
    min_n: int = 1,
    max_n: int = MAX_SHADOW_PROPERTY_QUBITS,
    max_terms: int = 3,
    max_obs: int = 2,
) -> tuple[Hamiltonian, OperatorSet, int]:
    """Draw a sparse Pauli ``(Hamiltonian, OperatorSet, n_qubits)`` model."""
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    n_terms = draw(st.integers(min_value=1, max_value=min(max_terms, max(1, 4**n - 1))))
    n_obs = draw(st.integers(min_value=1, max_value=min(max_obs, max(1, 4**n - 1))))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    scale = draw(st.floats(min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False))
    commuting = draw(st.sampled_from([True, False, None]))
    rng = np.random.default_rng(seed)
    ps = random_pauli_sum(rng, n, n_terms, scale, commuting=commuting)
    obs = observable_labels(rng, n, n_obs)
    return Hamiltonian(ps), OperatorSet(obs), n
