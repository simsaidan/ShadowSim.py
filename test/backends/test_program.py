"""Tests for the framework-neutral circuit program."""

import numpy as np
import pytest

from shadowsim.backends.program import Barrier, Hadamard, Measure, Prepare, Program, Reset, Unitary


def test_program_records_operations_and_copies_arrays():
    amplitudes = np.array([1.0, 0.0], dtype=np.complex128)
    matrix = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.complex128)
    program = Program(
        2,
        2,
        [
            Prepare(amplitudes, [1]),
            Unitary(matrix, [0]),
            Reset(0),
            Hadamard(1),
            Barrier([0, 1]),
            Measure(1, 0),
        ],
    )

    amplitudes[0] = 0.0
    matrix[0, 0] = 5.0

    assert program.num_qubits == 2
    assert program.num_clbits == 2
    assert program.operations[0] == Prepare([1.0, 0.0], [1])
    assert program.operations[1] == Unitary([[0.0, 1.0], [1.0, 0.0]], [0])
    assert program.operations[2:] == (Reset(0), Hadamard(1), Barrier([0, 1]), Measure(1, 0))
    assert program.operations[0] != program.operations[1]
    assert program.operations[2] != program.operations[3]
    assert program.operations[4] != program.operations[5]
    assert program == Program(program.num_qubits, program.num_clbits, program.operations)
    assert program != Program(2, 1, program.operations)
    assert program != object()
    with pytest.raises(ValueError):
        program.operations[0].amplitudes[0] = 0.0
    with pytest.raises(ValueError):
        program.operations[1].matrix[0, 0] = 0.0


def test_program_rejects_indexes_outside_the_register():
    with pytest.raises(ValueError, match="outside a program of 1 qubits"):
        Program(1, 1, [Hadamard(1)])
    with pytest.raises(ValueError, match="outside a program of 1 classical bits"):
        Program(1, 1, [Measure(0, 1)])


@pytest.mark.parametrize(
    "build",
    [
        lambda: Prepare("not-an-array", [0]),
        lambda: Prepare([1.0, 0.0, 0.0], [0]),
        lambda: Prepare([1.0], []),
        lambda: Prepare([1.0, 0.0], [0, 0]),
        lambda: Prepare([1.0, 0.0], [-1]),
        lambda: Unitary(np.eye(2), [0, 1]),
        lambda: Unitary(np.eye(1), []),
        lambda: Hadamard(True),
        lambda: Reset(-1),
        lambda: Barrier([]),
        lambda: Measure(0, -1),
        lambda: Program(-1, 0, []),
        lambda: Program(1, 0, ["h"]),
    ],
)
def test_program_rejects_invalid_operations(build):
    with pytest.raises((TypeError, ValueError)):
        build()
