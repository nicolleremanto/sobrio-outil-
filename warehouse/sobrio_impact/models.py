"""Type de sortie unique du module d'impact : l'intervalle min–max."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Range:
    """Intervalle min–max avec périmètre et source.

    Seul type de sortie autorisé pour un chiffre d'impact (règle n°3).
    Un `Range` sans périmètre (`scope`) ou avec min > max est invalide.
    """

    min: float
    max: float
    scope: str
    source: str

    def __post_init__(self) -> None:
        if self.min > self.max:
            raise ValueError(f"Range invalide : min ({self.min}) > max ({self.max})")
        if not self.scope:
            raise ValueError("Range sans périmètre (scope) interdit")
        if not self.source:
            raise ValueError("Range sans source interdit")
