"""Collections of Hamiltonian operators."""

from collections.abc import Iterator, Sequence

from shadowsim.core.hamiltonian import Hamiltonian
from shadowsim.core.pauli_string import PauliString
from shadowsim.core.pauli_sum import PauliSum


class HamiltonianSet:
    """Represents a set of quantum Hamiltonians."""

    def __init__(self, hamiltonians: Sequence[Hamiltonian | str | PauliString | PauliSum]) -> None:
        """Initialize a HamiltonianSet of quantum Hamiltonians.

        Parameter hamiltonians: Hamiltonians, or values coercible via
            :class:`Hamiltonian` (Pauli strings / expressions / PauliSum).
        """
        assert isinstance(hamiltonians, list), "hamiltonians must be a list"
        coerced: list[Hamiltonian] = []
        for h in hamiltonians:
            if isinstance(h, Hamiltonian):
                coerced.append(h)
            elif isinstance(h, (str, PauliString, PauliSum)):
                coerced.append(Hamiltonian(h))
            else:
                assert False, "all hamiltonians must be Hamiltonian objects"
        self.hamiltonians = coerced
        self.hamiltonian_count = len(coerced)

    def __str__(self) -> str:
        """Return a string representation of the HamiltonianSet."""
        return f"HamiltonianSet(hamiltonian_count={self.hamiltonian_count})"

    def __repr__(self) -> str:
        """Return a string representation of the HamiltonianSet."""
        return f"HamiltonianSet(hamiltonians={self.hamiltonians!r})"

    def __iter__(self) -> Iterator[Hamiltonian]:
        """Return an iterator over the Hamiltonians in the HamiltonianSet."""
        return iter(self.hamiltonians)

    def __len__(self) -> int:
        """Return the number of Hamiltonians in the HamiltonianSet."""
        return self.hamiltonian_count

    def __getitem__(self, index: int) -> Hamiltonian:
        """Return the Hamiltonian at the given index."""
        return self.hamiltonians[index]

    def __contains__(self, item: Hamiltonian) -> bool:
        """Return whether the HamiltonianSet contains the given Hamiltonian."""
        return item in self.hamiltonians
