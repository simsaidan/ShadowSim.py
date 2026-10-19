"""Measurement-count reducers shared by simulators and models."""


def population_one(counts: dict[str, int]) -> float:
    """Return the empirical probability of measuring '1'."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return counts.get("1", 0) / total


def expectation_z(counts: dict[str, int]) -> float:
    """Return the empirical expectation of Pauli Z on one qubit.

    A measured ``0`` contributes ``+1`` and a measured ``1`` contributes ``-1``.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return (counts.get("0", 0) - counts.get("1", 0)) / total


def expectation_x(counts: dict[str, int]) -> float:
    """Return the empirical expectation of Pauli X on one qubit.

    Counts must already be measured in the X basis. A measured ``0`` contributes
    ``+1`` and a measured ``1`` contributes ``-1``.
    """
    return expectation_z(counts)


def cavity_population(counts: dict[str, int]) -> float:
    """Cavity population reducer for two-bit cavity readout.

    Uses notebook convention:
      population = (3*N("11") + 2*N("10") + 1*N("01")) / shots
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return (3 * counts.get("11", 0) + 2 * counts.get("10", 0) + counts.get("01", 0)) / total
