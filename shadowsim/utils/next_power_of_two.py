"""Helpers for rounding up to a power of two."""


def next_power_of_two(n):
    """Return the first power of two greater than or equal to ``n``.

    ``next_power_of_two(5)`` returns 8 and ``next_power_of_two(8)`` returns 8.
    """
    assert isinstance(n, int), "n must be an integer"
    assert n >= 0, "n must be non-negative"

    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()
