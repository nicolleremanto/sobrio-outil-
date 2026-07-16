"""Module d'impact Sobrio.

Règle n°3 (non négociable) : tout chiffre d'impact est un **intervalle min–max
avec périmètre**. Ce module ne peut structurellement pas retourner une valeur
unique : `estimate()` retourne un `Range`, jamais un scalaire (test dédié dans
warehouse/tests/). Jamais d'équivalents grand public (litres, arbres, km).
"""

from .estimate import catalog_version, estimate
from .models import Range

__all__ = ["Range", "catalog_version", "estimate"]
