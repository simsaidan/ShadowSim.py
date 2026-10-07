"""Reusable physical model factories."""

from shadowsim.models.ising import IsingModel, ising
from shadowsim.models.tavis_cummings import TavisCummingsModel, tavis_cummings

__all__ = [
    "IsingModel",
    "TavisCummingsModel",
    "ising",
    "tavis_cummings",
]
