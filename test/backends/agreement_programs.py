"""Programs shared by the statevector agreement tests.

Named gates other than Hadamard are dense unitaries. Qubit 0 is the least
significant bit of each matrix, the same convention ``from_qiskit`` records.
"""

import numpy as np

from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Unitary

_X = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
_Y = np.array([[0.0, -1j], [1j, 0.0]], dtype=np.complex128)
_Z = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.complex128)
_S = np.array([[1.0, 0.0], [0.0, 1j]], dtype=np.complex128)
_S_DAGGER = np.array([[1.0, 0.0], [0.0, -1j]], dtype=np.complex128)
_T = np.array([[1.0, 0.0], [0.0, np.exp(1j * np.pi / 4)]], dtype=np.complex128)
_T_DAGGER = np.array([[1.0, 0.0], [0.0, np.exp(-1j * np.pi / 4)]], dtype=np.complex128)
_SX = np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=np.complex128) / 2
_SX_DAGGER = np.array([[1 - 1j, 1 + 1j], [1 + 1j, 1 - 1j]], dtype=np.complex128) / 2
# Control is qubit 0, the least significant bit. Target is qubit 1.
_CX = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ],
    dtype=np.complex128,
)
_CZ = np.diag([1.0, 1.0, 1.0, -1.0]).astype(np.complex128)
_SWAP = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.complex128,
)


def _rotation(theta: float, kind: str) -> np.ndarray:
    """Return one Qiskit ``rx``, ``ry``, or ``rz`` matrix."""
    half = theta / 2.0
    cosine = np.cos(half)
    sine = np.sin(half)
    if kind == "rx":
        return np.array([[cosine, -1j * sine], [-1j * sine, cosine]], dtype=np.complex128)
    if kind == "ry":
        return np.array([[cosine, -sine], [sine, cosine]], dtype=np.complex128)
    phase = np.exp(1j * half)
    return np.array([[1.0 / phase, 0.0], [0.0, phase]], dtype=np.complex128)


def _dense_unitary() -> np.ndarray:
    """Return one fixed 4 by 4 unitary, matching the old agreement fixture."""
    raw = np.random.default_rng(0).normal(size=(4, 4)) + 1j * np.random.default_rng(1).normal(size=(4, 4))
    unitary, _ = np.linalg.qr(raw)
    return np.asarray(unitary, dtype=np.complex128)


def programs() -> list[Program]:
    """Return the small programs used for the NumPy statevector comparison."""
    amplitude = np.sqrt(1.0 - 0.01 - 0.09 - 0.04)
    hadamard = Program(1, 0, [Hadamard(0)])
    rotation = Program(1, 0, [Unitary(_rotation(0.4, "rx"), (0,)), Unitary(_S, (0,))])
    bell = Program(2, 0, [Hadamard(0), Unitary(_CX, (0, 1))])
    prepared = Program(
        2,
        0,
        [
            Prepare([0.1, 0.3, 0.2, amplitude], (1, 0)),
            Barrier((0, 1)),
            Hadamard(0),
        ],
    )
    dense = Program(2, 0, [Unitary(_dense_unitary(), (1, 0))])
    named = Program(
        2,
        0,
        [
            Hadamard(0),
            Unitary(_X, (1,)),
            Unitary(_Y, (0,)),
            Unitary(_Z, (1,)),
            Unitary(_S, (0,)),
            Unitary(_S_DAGGER, (1,)),
            Unitary(_T, (0,)),
            Unitary(_T_DAGGER, (1,)),
            Unitary(_SX, (0,)),
            Unitary(_SX_DAGGER, (1,)),
            Unitary(_CX, (0, 1)),
            Unitary(_CZ, (1, 0)),
            Unitary(_SWAP, (0, 1)),
            Unitary(_rotation(0.3, "rx"), (0,)),
            Unitary(_rotation(-0.2, "ry"), (1,)),
            Unitary(_rotation(0.5, "rz"), (0,)),
        ],
    )
    return [hadamard, rotation, bell, prepared, dense, named]


def hadamard_counts() -> Program:
    """Return a Hadamard followed by a measurement of qubit 0."""
    return Program(1, 1, [Hadamard(0), Measure(0, 0)])
