"""Tests for src.core.utils helpers."""

import numpy as np
import pytest

from src.core.utils import flip_dict


@pytest.mark.parametrize(
    "d, expected",
    [
        ({}, {}),
        ({"01": 2}, {"10": 2}),
        ({"001": 1, "110": 2, "a": 3}, {"100": 1, "011": 2, "a": 3}),
        ({"aba": 7}, {"aba": 7}),
    ],
)
def test_flip_dict_reverses_keys(d, expected):
    assert flip_dict(d) == expected


def test_flip_dict_preserves_value_types():
    arr = np.array([1, 2])
    d = {"xy": 1, "zz": "hello", "ab": [1, 2, 3], "01": arr}
    out = flip_dict(d)
    assert out["yx"] == 1
    assert out["zz"] == "hello"
    assert out["ba"] == [1, 2, 3]
    assert out["10"] is arr


def test_flip_dict_does_not_mutate_input():
    d = {"01": 0, "ab": 1}
    d_copy = dict(d)
    _ = flip_dict(d)
    assert d == d_copy


def test_flip_dict_returns_new_dict():
    d = {"0": 1}
    out = flip_dict(d)
    assert out is not d
    out["0"] = 99
    assert d == {"0": 1}
