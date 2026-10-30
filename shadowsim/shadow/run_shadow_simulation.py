"""Helpers and result type for running shadow dynamics."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from shadowsim._optional import import_optional
from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian
from shadowsim.core.operator import Operator
from shadowsim.core.operator_set import OperatorSet
from shadowsim.core.state import State
from shadowsim.shadow.shadow_hamiltonian import ShadowHamiltonian, _infer_num_qubits
from shadowsim.shadow.shadow_state import ShadowState
from shadowsim.utils.next_power_of_two import next_power_of_two


@dataclass(frozen=True)
class ShadowSimulationResult:
    """Outputs from a shadow-space dynamics run.

    ``save`` writes ``times.npy``, ``expectations.npy``, and ``meta.json``.
    ``load`` restores times, curves, labels, basis, and padding, and leaves
    ``shadow_hamiltonian``, ``shadow_state``, and ``H_S_padded`` as ``None``.
    ``plot_results`` draws one expectation curve per label.

    Attributes:
        times: Simulation time grid.
        expectations: One expectation trajectory per shadow-space observable.
        labels: Names for each trajectory in ``expectations``.
        basis: Closure basis order (Pauli labels).
        shadow_num_qubits: Qubit count of the padded shadow Hilbert space.
        h_s_dimension: Unpadded ``H_S`` dimension, ``len(basis)``.
        shadow_hamiltonian: Constructed shadow Hamiltonian (includes unpadded ``H_S``).
            ``None`` when this result was not produced by a fresh run.
        shadow_state: Shadow state aligned to the closure basis order.
            ``None`` when this result was not produced by a fresh run.
        H_S_padded: ``H_S`` embedded in the top-left of a ``2**shadow_num_qubits`` matrix.
            ``None`` when this result was not produced by a fresh run.
    """

    times: npt.NDArray[np.float64]
    expectations: list[npt.NDArray[np.float64]]
    labels: list[str]
    basis: list[str]
    shadow_num_qubits: int
    h_s_dimension: int
    shadow_hamiltonian: ShadowHamiltonian | None = None
    shadow_state: ShadowState | None = None
    H_S_padded: npt.NDArray[np.complexfloating] | None = None

    def save(self, path: str | Path) -> Path:
        """Write times, expectation curves, and metadata to a directory.

        Layout::

            path/
              times.npy
              expectations.npy
              meta.json

        ``expectations.npy`` is a float64 array of shape
        ``(len(labels), len(times))``, one curve per row. ``meta.json`` records
        ``labels``, ``basis``, ``shadow_num_qubits``, and ``h_s_dimension``.
        The shadow Hamiltonian, shadow state, and padded ``H_S`` are not written.
        Arrays are saved with ``allow_pickle=False``.
        """
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        times = _as_time_grid(self.times)
        expectations = _as_expectation_matrix(times, self.labels, self.expectations)
        np.save(out / "times.npy", times, allow_pickle=False)
        np.save(out / "expectations.npy", expectations, allow_pickle=False)
        meta = {
            "basis": list(self.basis),
            "h_s_dimension": int(self.h_s_dimension),
            "labels": list(self.labels),
            "shadow_num_qubits": int(self.shadow_num_qubits),
        }
        (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: str | Path) -> "ShadowSimulationResult":
        """Reload a result previously written by ``save``.

        Restores times, expectation curves, labels, basis, and padding.
        ``shadow_hamiltonian``, ``shadow_state``, and ``H_S_padded`` are
        ``None``. Array files are read with ``allow_pickle=False``. A pickle
        payload is rejected and not executed.
        """
        root = Path(path)
        if not root.is_dir():
            raise FileNotFoundError(f"ShadowSimulationResult directory not found: {root}")
        labels, basis, shadow_num_qubits, h_s_dimension = _load_meta(root)
        times = _as_time_grid(_read_npy(root / "times.npy"))
        expectations = _expectations_from_array(_read_npy(root / "expectations.npy"), times, labels)
        if len(basis) != h_s_dimension:
            raise ValueError(
                f"basis length disagrees with h_s_dimension; got {len(basis)} labels and h_s_dimension={h_s_dimension}"
            )
        if next_power_of_two(h_s_dimension) != 1 << shadow_num_qubits:
            raise ValueError(
                "shadow padding disagrees with h_s_dimension; "
                f"got h_s_dimension={h_s_dimension}, shadow_num_qubits={shadow_num_qubits}"
            )
        return cls(
            times=times,
            expectations=expectations,
            labels=labels,
            basis=basis,
            shadow_num_qubits=shadow_num_qubits,
            h_s_dimension=h_s_dimension,
        )

    def plot_results(self, *, title: str | None = None) -> None:
        """Plot expectation traces against time in an interactive window.

        One curve is drawn per entry of ``labels``. Axis labels are ``Time`` and
        ``Expectation``. Matplotlib is imported through the ``viz`` extra.
        """
        plt = import_optional("matplotlib.pyplot", extra="viz")
        for label, trace in zip(self.labels, self.expectations, strict=True):
            plt.plot(self.times, trace, label=label)
        if title:
            plt.title(title)
        plt.xlabel("Time")
        plt.ylabel("Expectation")
        plt.legend()
        plt.show()


# Integer and real floating arrays. Complex and object arrays are excluded:
# object arrays are pickles, and these traces are real expectation values.
_REAL_KINDS = frozenset("iuf")


def _as_time_grid(values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Return ``values`` as a 1D float64 time grid."""
    array = _real_array(values, "times")
    if array.ndim != 1:
        raise ValueError(f"times must be a 1D array, got shape {array.shape}")
    return np.asarray(array, dtype=np.float64)


def _as_expectation_matrix(
    times: npt.NDArray[np.float64],
    labels: Sequence[str],
    expectations: Sequence[npt.ArrayLike],
) -> npt.NDArray[np.float64]:
    """Stack one expectation curve per label into a ``(n_labels, n_times)`` array."""
    if len(labels) != len(expectations):
        raise ValueError(f"labels and expectations disagree; got {len(labels)} labels and {len(expectations)} curves")
    rows: list[npt.NDArray[np.float64]] = []
    for index, curve in enumerate(expectations):
        array = _real_array(curve, f"expectations[{index}]")
        if array.ndim != 1 or array.shape[0] != times.shape[0]:
            raise ValueError(
                "expectation length disagrees with times; "
                f"curve {index} has shape {array.shape}, times has length {times.shape[0]}"
            )
        rows.append(np.asarray(array, dtype=np.float64))
    if not rows:
        return np.zeros((0, times.shape[0]), dtype=np.float64)
    return np.stack(rows)


def _expectations_from_array(
    raw: np.ndarray,
    times: npt.NDArray[np.float64],
    labels: Sequence[str],
) -> list[npt.NDArray[np.float64]]:
    """Split a saved ``(n_labels, n_times)`` array into one curve per label."""
    array = _real_array(raw, "expectations.npy")
    if array.ndim != 2:
        raise ValueError(f"expectations.npy must be a 2D array, got shape {array.shape}")
    if array.shape[0] != len(labels) or array.shape[1] != times.shape[0]:
        raise ValueError(
            "expectations.npy disagrees with labels and times; "
            f"got shape {array.shape}, {len(labels)} labels, and times length {times.shape[0]}"
        )
    return [np.asarray(row, dtype=np.float64) for row in array]


def _real_array(values: npt.ArrayLike, label: str) -> np.ndarray:
    """Return ``values`` when it is a real numeric array."""
    array = np.asarray(values)
    if array.dtype.hasobject or array.dtype.kind not in _REAL_KINDS:
        raise ValueError(f"{label} must be a real numeric array, got dtype {array.dtype}")
    return array


def _read_npy(path: Path) -> np.ndarray:
    """Load ``path`` with ``allow_pickle=False`` and copy the array."""
    if not path.is_file():
        raise FileNotFoundError(f"missing {path.name} in {path.parent}")
    try:
        loaded = np.load(path, allow_pickle=False)
    except ValueError as exc:
        if "pickle" in str(exc).lower():
            raise ValueError(f"{path.name} contains a pickle payload and was not loaded") from exc
        raise
    if not isinstance(loaded, np.ndarray):
        close = getattr(loaded, "close", None)
        if callable(close):
            close()
        raise ValueError(f"expected an array in {path.name}")
    return np.array(loaded, copy=True)


def _load_meta(root: Path) -> tuple[list[str], list[str], int, int]:
    """Read labels, basis, ``shadow_num_qubits``, and ``h_s_dimension`` from ``meta.json``."""
    meta_path = root / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing meta.json in {root}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ValueError("meta.json must be an object")
    return (
        _string_list(meta.get("labels"), "labels"),
        _string_list(meta.get("basis"), "basis"),
        _nonnegative_int(meta.get("shadow_num_qubits"), "shadow_num_qubits"),
        _nonnegative_int(meta.get("h_s_dimension"), "h_s_dimension"),
    )


def _string_list(value: object, label: str) -> list[str]:
    """Return ``value`` when it is a list of strings."""
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)


def _nonnegative_int(value: object, label: str) -> int:
    """Return ``value`` when it is a non-negative integer and not a bool."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def computational_basis_projectors(num_qubits: int) -> OperatorSet:
    """Return computational-basis projectors on a ``num_qubits``-qubit space.

    For ``n`` qubits this yields ``2**n`` rank-1 projectors ``|k⟩⟨k|`` labeled
    ``P_{bits}`` (e.g. ``P_00``, ``P_01``, …).
    """
    if num_qubits < 0:
        raise ValueError(f"num_qubits must be non-negative, got {num_qubits}")
    dim = 1 << num_qubits
    ops: list[Operator] = []
    for i in range(dim):
        bits = format(i, f"0{num_qubits}b") if num_qubits > 0 else ""
        p = np.zeros((dim, dim), dtype=np.complex128)
        p[i, i] = 1.0
        ops.append(Operator(p, name=f"P_{bits}" if num_qubits > 0 else "P_"))
    return OperatorSet(ops)


def pad_h_s(H_S: npt.NDArray[np.complexfloating]) -> tuple[npt.NDArray[np.complexfloating], int]:
    """Embed ``H_S`` in the top-left of the next power-of-two square matrix.

    Returns:
        ``(H_S_padded, shadow_num_qubits)`` where ``H_S_padded`` has shape
        ``(D, D)`` with ``D = next_power_of_two(m)`` for an ``m×m`` input, and
        ``shadow_num_qubits = log2(D)`` (``0`` when ``D == 1``).
    """
    matrix = np.asarray(H_S, dtype=np.complex128)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"H_S must be a square matrix, got shape {matrix.shape}")
    m = int(matrix.shape[0])
    d = next_power_of_two(m)
    if d == m:
        padded = matrix.copy()
    else:
        padded = np.zeros((d, d), dtype=np.complex128)
        padded[:m, :m] = matrix
    shadow_num_qubits = d.bit_length() - 1
    return padded, shadow_num_qubits


def _as_hamiltonian_list(hamiltonians: Hamiltonian | Sequence[Hamiltonian]) -> list[Hamiltonian]:
    if isinstance(hamiltonians, Hamiltonian):
        return [hamiltonians]
    terms = list(hamiltonians)
    if not terms:
        raise ValueError("shadow simulation: hamiltonians must be a non-empty sequence")
    return terms


def _as_operator_set(observables: OperatorSet | Sequence[Operator | str]) -> OperatorSet:
    if isinstance(observables, OperatorSet):
        ops = observables
    else:
        ops = OperatorSet(list(observables))
    if len(ops) == 0:
        raise ValueError("shadow simulation: observables must be non-empty")
    return ops


def _validate_physical_dims(
    terms: list[Hamiltonian],
    observables: OperatorSet,
    initial_state: State,
    num_qubits: int,
) -> None:
    expected_dim = 2**num_qubits
    state_nq = initial_state.get_num_qubits()
    if state_nq != num_qubits:
        raise ValueError(
            "shadow simulation: initial_state qubit count disagrees with num_qubits; "
            f"got state num_qubits={state_nq}, expected {num_qubits}"
        )
    if initial_state.state.shape[0] != expected_dim:
        raise ValueError(
            "shadow simulation: initial_state dimension disagrees with num_qubits; "
            f"got length {initial_state.state.shape[0]}, expected {expected_dim}"
        )
    for h in terms:
        if isinstance(h, LocalHamiltonian):
            continue
        if int(h.dimension) != expected_dim:
            raise ValueError(
                "shadow simulation: Hamiltonian dimension disagrees with num_qubits; "
                f"got dimension {h.dimension}, expected {expected_dim}"
            )
    for op in observables.operators:
        if int(op.dimension) != expected_dim:
            raise ValueError(
                "shadow simulation: observable dimension disagrees with num_qubits; "
                f"got dimension {op.dimension}, expected {expected_dim}"
            )


def run_shadow_simulation(
    hamiltonians: Hamiltonian | Sequence[Hamiltonian],
    observables: OperatorSet | Sequence[Operator | str],
    initial_state: State,
    *,
    total_time: float,
    time_steps: int,
    num_qubits: int | None = None,
    shadow_observables: OperatorSet | None = None,
    tol: float = 1e-10,
    verbose: bool = False,
) -> ShadowSimulationResult:
    """Build the shadow model and evolve it with ``QutipSimulator``.

    Constructs ``ShadowHamiltonian`` on the physical system, builds a
    ``ShadowState`` ordered to match the closure basis of ``H_S``, pads
    ``H_S`` to a power-of-two Hilbert space, and simulates with QuTiP.
    Default shadow-space observables are computational-basis projectors.

    Example:
        ```python
        import numpy as np
        from shadowsim.core import Hamiltonian, OperatorSet, State
        from shadowsim.shadow import run_shadow_simulation

        result = run_shadow_simulation(
            Hamiltonian("X"),
            OperatorSet(["Z"]),
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            total_time=1.0,
            time_steps=11,
        )
        print(result.shadow_num_qubits, result.shadow_hamiltonian.basis)
        ```
    """
    terms = _as_hamiltonian_list(hamiltonians)
    operator_set = _as_operator_set(observables)
    nq = num_qubits if num_qubits is not None else _infer_num_qubits(terms)
    if nq < 0:
        raise ValueError(f"shadow simulation: num_qubits must be non-negative, got {nq}")
    _validate_physical_dims(terms, operator_set, initial_state, nq)

    shadow_h = ShadowHamiltonian(
        operator_set,
        terms,
        num_qubits=nq,
        tol=tol,
        verbose=verbose,
    )
    H_S_padded, shadow_nq = pad_h_s(shadow_h.H_S)
    closure_ops = OperatorSet(list(shadow_h.basis))
    shadow_state = ShadowState(initial_state, closure_ops, num_qubits=shadow_nq)

    if shadow_state.get_num_qubits() != shadow_nq:
        raise ValueError(
            "shadow simulation: padded shadow state qubit count disagrees with padded H_S; "
            f"got state num_qubits={shadow_state.get_num_qubits()}, expected {shadow_nq}"
        )
    if shadow_state.state.shape[0] != H_S_padded.shape[0]:
        raise ValueError(
            "shadow simulation: padded shadow state dimension disagrees with padded H_S; "
            f"got state length {shadow_state.state.shape[0]}, H_S shape {H_S_padded.shape}"
        )

    e_ops = shadow_observables if shadow_observables is not None else computational_basis_projectors(shadow_nq)
    if len(e_ops) == 0:
        raise ValueError("shadow simulation: shadow_observables must be non-empty")
    expected_shadow_dim = 1 << shadow_nq
    for op in e_ops.operators:
        if int(op.dimension) != expected_shadow_dim:
            raise ValueError(
                "shadow simulation: shadow_observables dimension disagrees with shadow space; "
                f"got dimension {op.dimension}, expected {expected_shadow_dim}"
            )

    qutip_simulator = import_optional("shadowsim.simulators.qutip_simulator", extra="qutip")
    simulator = qutip_simulator.QutipSimulator(
        [Hamiltonian(H_S_padded)],
        [],
        shadow_state,
        e_ops,
        num_qubits=shadow_nq,
        total_time=total_time,
        time_steps=time_steps,
    )
    simulator.simulate()
    expectations = [np.asarray(curve, dtype=np.float64) for curve in simulator.get_results()]
    labels = [op.name if op.name is not None else str(i) for i, op in enumerate(e_ops)]

    return ShadowSimulationResult(
        times=np.asarray(simulator.tlist, dtype=np.float64),
        expectations=expectations,
        labels=labels,
        basis=list(shadow_h.basis),
        shadow_num_qubits=shadow_nq,
        h_s_dimension=int(shadow_h.H_S.shape[0]),
        shadow_hamiltonian=shadow_h,
        shadow_state=shadow_state,
        H_S_padded=H_S_padded,
    )
