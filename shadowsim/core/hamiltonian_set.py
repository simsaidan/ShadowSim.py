"""Collections of Hamiltonian operators."""

from shadowsim.core.hamiltonian import Hamiltonian


class HamiltonianSet:
    """Represents a set of quantum Hamiltonians."""

    def __init__(self, hamiltonians: list[Hamiltonian]):
        """Initialize a HamiltonianSet of quantum Hamiltonians.

        Parameter hamiltonians: The list of Hamiltonians to initialize the HamiltonianSet with.
        Precondition: hamiltonians is a list of Hamiltonian objects.
        """
        assert isinstance(hamiltonians, list), "hamiltonians must be a list"
        assert all(isinstance(h, Hamiltonian) for h in hamiltonians), "all hamiltonians must be Hamiltonian objects"
        self.hamiltonians = hamiltonians
        self.hamiltonian_count = len(hamiltonians)

    def __str__(self):
        """Return a string representation of the HamiltonianSet."""
        return f"HamiltonianSet(hamiltonian_count={self.hamiltonian_count})"

    def __repr__(self):
        """Return a string representation of the HamiltonianSet."""
        return f"HamiltonianSet(hamiltonians={self.hamiltonians!r})"

    def __iter__(self):
        """Return an iterator over the Hamiltonians in the HamiltonianSet."""
        return iter(self.hamiltonians)

    def __len__(self):
        """Return the number of Hamiltonians in the HamiltonianSet."""
        return self.hamiltonian_count

    def __getitem__(self, index: int):
        """Return the Hamiltonian at the given index."""
        return self.hamiltonians[index]

    def __contains__(self, item: Hamiltonian):
        """Return whether the HamiltonianSet contains the given Hamiltonian."""
        return item in self.hamiltonians
