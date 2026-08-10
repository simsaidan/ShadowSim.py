"""Helpers for reversing dictionary keys (bitstring endianness)."""

from typing import Any


def flip_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Return a new dictionary with each string key reversed.

    Measurement outcomes are often labeled by bitstrings whose endianness
    differs between frameworks; reversing the keys converts between those
    conventions.

    Args:
        d: Mapping whose keys are strings (typically measurement bitstrings).

    Returns:
        A new dictionary with the same values and each key reversed.

    Examples:
        Flip Qiskit-style bitstring keys:

        ```python exec="1" source="above" result="text"
        from shadowsim.utils.flip_dict import flip_dict

        print(flip_dict({"01": 3, "10": 5}))
        ```

    """
    return {k[::-1]: v for k, v in d.items()}
