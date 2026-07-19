import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_hamiltonian import LocalHamiltonian


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

    Parameter hamiltonians: The list of Hamiltonians to sum.
    Precondition: hamiltonians is a list of Hamiltonian objects.

    Parameter num_qubits: The number of qubits in the full system.
    Precondition: num_qubits is a positive integer.
    """
    assert isinstance(hamiltonians, list), "hamiltonians must be a list"
    assert all(
        isinstance(h, Hamiltonian) for h in hamiltonians
    ), "all hamiltonians must be Hamiltonian objects"
    assert isinstance(num_qubits, int), "num_qubits must be an integer"
    assert num_qubits > 0, "num_qubits must be a positive integer"
    assert len(hamiltonians) > 0, "hamiltonians must be a non-empty list"

    local_dims = {h.local_dim for h in hamiltonians if isinstance(h, LocalHamiltonian)}
    if len(local_dims) > 1:
        raise ValueError(
            f"mixed local_dim in LocalHamiltonian terms is not supported: {sorted(local_dims)}"
        )

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
