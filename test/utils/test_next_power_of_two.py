import pytest

from src.utils.next_power_of_two import next_power_of_two


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 4),
        (4, 4),
        (5, 8),
        (7, 8),
        (8, 8),
        (9, 16),
        (15, 16),
        (16, 16),
        (17, 32),
        (1023, 1024),
        (1024, 1024),
    ],
)
def test_next_power_of_two(n, expected):
    assert next_power_of_two(n) == expected


def test_next_power_of_two_rejects_negative():
    with pytest.raises(AssertionError):
        next_power_of_two(-1)


def test_next_power_of_two_rejects_non_int():
    with pytest.raises(AssertionError):
        next_power_of_two(3.0)
