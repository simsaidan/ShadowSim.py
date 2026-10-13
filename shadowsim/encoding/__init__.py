"""Prepare a normalized quantum state from classical data.

``encode`` returns a ``State`` that any simulator accepts as ``initial_state``.
``load_encoding_data`` reads a 1D vector from a ``.npy``, ``.txt``, or ``.csv`` file.
"""

from shadowsim.encoding.amplitude import AmplitudeEncoding
from shadowsim.encoding.angle import AngleEncoding
from shadowsim.encoding.computational_basis import ComputationalBasisEncoding
from shadowsim.encoding.gray import GrayEncoding
from shadowsim.encoding.load import load_encoding_data
from shadowsim.encoding.state_encoder import StateEncoder

__all__ = [
    "AmplitudeEncoding",
    "AngleEncoding",
    "ComputationalBasisEncoding",
    "GrayEncoding",
    "StateEncoder",
    "load_encoding_data",
]
