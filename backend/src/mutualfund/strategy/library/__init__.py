"""Concrete, designer-selectable strategies (REQUIREMENTS §5.8.1)."""

from .momentum import MomentumStrategy
from .sma_cross import SmaCrossStrategy

__all__ = ["MomentumStrategy", "SmaCrossStrategy"]
