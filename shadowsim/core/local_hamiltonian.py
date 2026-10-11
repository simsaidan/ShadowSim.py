"""Local Hamiltonian terms on contiguous sites."""

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import _Matrix
from shadowsim.utils.hermitian import hermitian
from shadowsim.utils.tensor import tensor


class LocalHamiltonian(LocalOperator, Hamiltonian):
    """Local Hamiltonian acting non-trivially on the provided sites.

    ``sites`` must be distinct consecutive integers; see `LocalOperator`.
    """

    def __init__(
        self,
        matrix: _Matrix,
        sites: list[int],
        local_dim: int = 2,
    ) -> None:
        """Initialize a LocalHamiltonian on contiguous sites."""
        if isinstance(matrix, np.ndarray):
            if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
                raise ValueError(f"matrix must be a square 2D array; got shape {matrix.shape}")
            if not hermitian(matrix):
                raise ValueError(f"matrix must be Hermitian; got shape {matrix.shape}")
        super().__init__(matrix, sites, local_dim)

    def to_full_hamiltonian(self, total_sites: int) -> Hamiltonian:
        """Return a FullHamiltonian for this local term on the given sites.

        Parameter total_sites: The total number of sites in the full system.
        Precondition: total_sites is a positive integer.
        """
        if not isinstance(total_sites, int):
            raise TypeError(f"total_sites must be an integer; got {type(total_sites)!r}")
        if total_sites < 1:
            raise ValueError(f"total_sites must be positive; got {total_sites}")

        lo, hi = min(self.sites), max(self.sites)
        if lo < 0:
            raise ValueError(f"site indices must be non-negative; got {self.sites}")
        if hi >= total_sites:
            raise ValueError(f"total_sites={total_sites} is too small for local sites {self.sites}")

        eye = np.eye(self.local_dim, dtype=self.matrix.dtype)
        left_id = [eye] * lo
        right_id = [eye] * (total_sites - hi - 1)
        full_matrix = tensor(left_id + [self.matrix] + right_id)
        return Hamiltonian(full_matrix)

    def get_sites(self) -> list[int]:
        """Return the sites on which the local Hamiltonian acts non-trivially."""
        return self.sites

    def get_local_dim(self) -> int:
        """Return the local dimension of the local Hamiltonian."""
        return self.local_dim

    def get_matrix(self) -> _Matrix:
        """Return the matrix representation of the local Hamiltonian."""
        return self.matrix

    def __str__(self) -> str:
        """Return a string representation of the LocalHamiltonian."""
        return f"LocalHamiltonian(sites={self.sites}, local_dim={self.local_dim}, shape={self.matrix.shape})"

    def __repr__(self) -> str:
        """Return a string representation of the LocalHamiltonian."""
        return f"LocalHamiltonian(matrix={self.matrix!r}, sites={self.sites!r}, local_dim={self.local_dim})"
