"""Linear combinations of Pauli strings."""

import re
from collections.abc import Iterable, Mapping
from typing import Self

import numpy as np

from shadowsim.core.pauli_string import PauliString

# Signed Python-like complex literal (no parentheses), e.g. 1, -0.5, 2j, -1+0.5j.
# Pure-imag forms are tried first so "1j" is not truncated to "1".
_COMPLEX = re.compile(
    r"""
    [+-]?
    (?:
        (?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[jJ]
        |
        (?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?
        (?:[+-](?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[jJ])?
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)
_LABEL = re.compile(r"[IXYZ]+", re.IGNORECASE)


def _format_term(label: str, coeff: complex, *, leading: bool) -> str:
    """Format one term for display."""
    real, imag = coeff.real, coeff.imag
    if np.isclose(imag, 0.0):
        value = float(real)
        if np.isclose(value, 1.0):
            body = label
            negative = False
        elif np.isclose(value, -1.0):
            body = label
            negative = True
        else:
            negative = value < 0
            body = f"{abs(value):g}*{label}"
    elif np.isclose(real, 0.0):
        value = float(imag)
        if np.isclose(abs(value), 1.0):
            body = f"1j*{label}"
            negative = value < 0
        else:
            negative = value < 0
            body = f"{abs(value):g}j*{label}"
    else:
        # General complex: keep Python-ish form without a leading '+' on the first term.
        c_str = str(coeff).replace("(", "").replace(")", "")
        negative = c_str.startswith("-")
        if negative:
            c_str = c_str[1:]
        body = f"{c_str}*{label}"

    if leading:
        return f"-{body}" if negative else body
    return f" - {body}" if negative else f" + {body}"


class PauliSum:
    """Sparse linear combination of equal-length Pauli words."""

    __slots__ = ("_terms",)

    def __init__(self, terms: Mapping[str, complex] | Iterable[tuple[str, complex]]):
        """Initialize from a label→coeff mapping or an iterable of pairs."""
        if isinstance(terms, Mapping):
            items = list(terms.items())
        else:
            items = list(terms)
        if not items:
            raise ValueError("PauliSum must contain at least one term")

        cleaned: dict[str, complex] = {}
        for label, coeff in items:
            if not isinstance(label, str):
                raise TypeError(f"Pauli label must be a string, got {type(label)!r}")
            lab = label.strip().upper().replace(" ", "")
            if not lab or _LABEL.fullmatch(lab) is None:
                raise ValueError(f"invalid Pauli word {label!r}")
            c = complex(coeff)
            if lab in cleaned:
                cleaned[lab] += c
            else:
                cleaned[lab] = c

        cleaned = {lab: c for lab, c in cleaned.items() if c != 0}
        if not cleaned:
            raise ValueError("PauliSum must contain at least one term")

        n = len(next(iter(cleaned)))
        if any(len(lab) != n for lab in cleaned):
            raise ValueError("all Pauli words in a PauliSum must have the same length")
        self._terms = cleaned

    @classmethod
    def from_string(cls, expr: str) -> Self:
        """Build a PauliSum from an expression such as ``XXI + XYZ``."""
        return parse_pauli_expression(expr)

    @classmethod
    def from_pauli_string(cls, pauli_string: PauliString, coeff: complex = 1 + 0j) -> Self:
        """Build a one-term PauliSum from a :class:`PauliString`."""
        return cls({str(pauli_string): coeff})

    @property
    def terms(self) -> dict[str, complex]:
        """Return a copy of the label→coefficient mapping."""
        return dict(self._terms)

    @property
    def num_qubits(self) -> int:
        """Return the number of qubits (length of each Pauli word)."""
        return len(next(iter(self._terms)))

    def is_hermitian(self, tol: float = 1e-12) -> bool:
        """Return whether all coefficients are real (within ``tol``)."""
        return all(abs(c.imag) <= tol for c in self._terms.values())

    def to_matrix(self) -> np.ndarray:
        """Return the dense matrix for this Pauli sum."""
        dim = 2**self.num_qubits
        out = np.zeros((dim, dim), dtype=np.complex128)
        for label, coeff in self._terms.items():
            out += coeff * PauliString.from_string(label).matrix()
        return out

    def __len__(self) -> int:
        """Return the number of nonzero Pauli terms."""
        return len(self._terms)

    def __str__(self) -> str:
        """Return a normalized expression string."""
        parts: list[str] = []
        for i, (label, coeff) in enumerate(self._terms.items()):
            parts.append(_format_term(label, coeff, leading=(i == 0)))
        return "".join(parts)

    def __repr__(self) -> str:
        """Return a developer-oriented representation."""
        return f"PauliSum({self._terms!r})"

    def __eq__(self, other: object) -> bool:
        """Return whether two Pauli sums have the same terms (up to coeff tolerance)."""
        if not isinstance(other, PauliSum):
            return NotImplemented
        if self._terms.keys() != other._terms.keys():
            return False
        return all(np.isclose(self._terms[k], other._terms[k]) for k in self._terms)

    __hash__ = None


def parse_pauli_expression(expr: str) -> PauliSum:
    """Parse a Pauli word or linear combination into a :class:`PauliSum`.

    Supports forms such as ``XII``, ``XXI + XYZ``, ``0.5*XXI - XYZ``,
    and ``-1+0.5j*XX``.
    """
    s = "".join(expr.split())
    if not s:
        raise ValueError("empty Pauli expression")

    terms: dict[str, complex] = {}
    order: list[str] = []
    pos = 0
    first = True

    while pos < len(s):
        if not first and s[pos] not in "+-":
            raise ValueError(f"expected '+' or '-' at position {pos} in {expr!r}")
        first = False

        coeff = 1 + 0j
        m_num = _COMPLEX.match(s, pos)
        if m_num is not None:
            coeff = complex(m_num.group(0).replace("J", "j"))
            pos = m_num.end()
            if pos < len(s) and s[pos] == "*":
                pos += 1
        elif s[pos] in "+-":
            coeff = 1 + 0j if s[pos] == "+" else -1 + 0j
            pos += 1

        m_lab = _LABEL.match(s, pos)
        if m_lab is None:
            raise ValueError(f"expected Pauli word at position {pos} in {expr!r}")
        label = m_lab.group(0).upper()
        pos = m_lab.end()

        if label not in terms:
            order.append(label)
            terms[label] = coeff
        else:
            terms[label] += coeff

    n = len(order[0])
    if any(len(lab) != n for lab in order):
        raise ValueError("all Pauli words in an expression must have the same length")

    # Drop exact zeros from cancellation (keep insertion order of survivors).
    cleaned = {lab: terms[lab] for lab in order if terms[lab] != 0}
    if not cleaned:
        raise ValueError("Pauli expression simplifies to the zero operator")
    return PauliSum(cleaned)
