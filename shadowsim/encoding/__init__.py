"""Prepare a normalized quantum state from classical data.

``encode`` returns a ``State`` that any simulator accepts as ``initial_state``.
"""

from shadowsim.encoding.amplitude import AmplitudeEncoding
from shadowsim.encoding.angle import AngleEncoding
from shadowsim.encoding.computational_basis import ComputationalBasisEncoding
from shadowsim.encoding.gray import GrayEncoding
from shadowsim.encoding.state_encoder import StateEncoder

__all__ = [
    "AmplitudeEncoding",
    "AngleEncoding",
    "ComputationalBasisEncoding",
    "GrayEncoding",
    "StateEncoder",
]
