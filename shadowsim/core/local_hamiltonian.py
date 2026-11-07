"""Local Hamiltonian terms on contiguous sites."""

import numpy as np

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.local_operator import LocalOperator
from shadowsim.core.operator import _Matrix
from shadowsim.utils.hermitian import hermitian


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
        """Return this local term embedded on ``total_sites`` sites.

        The embedding is `LocalOperator.to_full_operator`: ``sites[0]`` is the
        first tensor factor of the stored matrix.

        Parameter total_sites: The total number of sites in the full system.
        Precondition: total_sites is a positive integer.
        """
        return Hamiltonian(self.to_full_operator(total_sites).matrix)

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
