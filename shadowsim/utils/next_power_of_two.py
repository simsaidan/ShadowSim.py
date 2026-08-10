"""Helpers for rounding up to a power of two."""


def next_power_of_two(n: int) -> int:
    """Return the first power of two greater than or equal to ``n``.

    Useful when allocating padded Hilbert-space dimensions or buffer sizes that
    must be a power of two.

    Args:
        n: Non-negative integer.

    Returns:
        The smallest power of two that is at least ``n``. For ``n <= 1`` the
        result is ``1``.

    Raises:
        AssertionError: If ``n`` is not a non-negative integer.

    Examples:
        ```python exec="1" source="above" result="text"
        from shadowsim.utils.next_power_of_two import next_power_of_two

        print(next_power_of_two(5))
        print(next_power_of_two(8))
        ```

    """
    assert isinstance(n, int), "n must be an integer"
    assert n >= 0, "n must be non-negative"

    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()
