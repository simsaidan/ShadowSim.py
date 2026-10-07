"""Measurement-count reducers shared by simulators and models."""


def population_one(counts: dict[str, int]) -> float:
    """Return the empirical probability of measuring '1'."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return counts.get("1", 0) / total


def cavity_population(counts: dict[str, int]) -> float:
    """Cavity population reducer for two-bit cavity readout.

    Uses notebook convention:
      population = (3*N("11") + 2*N("10") + 1*N("01")) / shots
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return (3 * counts.get("11", 0) + 2 * counts.get("10", 0) + counts.get("01", 0)) / total
