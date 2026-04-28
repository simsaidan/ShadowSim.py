import numpy as np

from src.core.operator_set import LocalOperator, Operator


class Hamiltonian(Operator):
    def __init__(self, matrix: np.ndarray):
        super().__init__(matrix)

    def __str__(self):
        return f"Hamiltonian(matrix={self.matrix})"

    def __repr__(self):
        return f"Hamiltonian(matrix={self.matrix})"

    def __eq__(self, other):
        return np.allclose(self.matrix, other.matrix)

    def __ne__(self, other):
        return not np.allclose(self.matrix, other.matrix)

    def to_hamiltonian_set(self):
        return HamiltonianSet([self])

    def to_local_hamiltonian(self, local_dim: int = 2):
        lo = self.to_local_operator(local_dim)
        return LocalHamiltonian(lo.matrix, lo.sites, lo.local_dim)


class LocalHamiltonian(LocalOperator, Hamiltonian):
    """
    Local Hamiltonian acting non-trivially on the provided `sites`.

    ``sites`` must be distinct consecutive integers; see `LocalOperator`.
    """

    def __init__(
        self,
        matrix: np.ndarray,
        sites: list[int],
        local_dim: int = 2,
    ):
        super().__init__(matrix, sites, local_dim)

    def __str__(self):
        return (
            "LocalHamiltonian("
            f"sites={self.sites}, "
            f"local_dim={self.local_dim}, "
            f"shape={self.matrix.shape}"
            ")"
        )

    def __repr__(self):
        return (
            "LocalHamiltonian("
            f"matrix={self.matrix!r}, "
            f"sites={self.sites!r}, "
            f"local_dim={self.local_dim}"
            ")"
        )


class HamiltonianSet:
    def __init__(self, hamiltonians: list[Hamiltonian]):
        self.hamiltonians = hamiltonians
        self.hamiltonian_count = len(hamiltonians)

    def __str__(self):
        return f"HamiltonianSet(hamiltonian_count={self.hamiltonian_count})"

    def __repr__(self):
        return f"HamiltonianSet(hamiltonians={self.hamiltonians!r})"


def combined_hamiltonian_matrix(
    hamiltonians: list[Hamiltonian],
    num_qubits: int,
) -> np.ndarray:
    """
    Sum Hamiltonian terms on the full ``num_qubits``-site tensor space.

    ``LocalHamiltonian`` terms are embedded with identities on the remaining
    sites; full-domain ``Hamiltonian`` matrices are added as-is. All terms must
    match a common Hilbert-space dimension (``local_dim ** num_qubits`` for
    locals, or the matrix size of bare terms).
    """
    if not hamiltonians:
        raise ValueError("hamiltonians must be a non-empty list")

    target_dim: int | None = None
    for h in hamiltonians:
        if isinstance(h, LocalHamiltonian):
            d = h.local_dim**num_qubits
        else:
            d = int(np.asarray(h.matrix).shape[0])
        if target_dim is None:
            target_dim = d
        elif d != target_dim:
            raise ValueError(
                f"Hamiltonian dimensions disagree: got {d} vs {target_dim}"
            )

    H_tot = np.zeros((target_dim, target_dim), dtype=np.complex128)
    for h in hamiltonians:
        if isinstance(h, LocalHamiltonian):
            ld = h.local_dim
            lo, hi = min(h.sites), max(h.sites)
            n_before = lo
            n_after = num_qubits - 1 - hi
            term = np.asarray(h.matrix, dtype=np.complex128)
            if n_before > 0:
                term = np.kron(np.eye(ld**n_before, dtype=np.complex128), term)
            if n_after > 0:
                term = np.kron(term, np.eye(ld**n_after, dtype=np.complex128))
            H_tot += term
        else:
            H_tot += np.asarray(h.matrix, dtype=np.complex128)
    return H_tot
