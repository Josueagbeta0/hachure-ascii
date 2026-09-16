"""Mise en forme de la luminosité, appliquée avant le choix des caractères.

Une correspondance linéaire entre luminosité et rampe gaspille l'essentiel de
celle-ci sur des images ordinaires : une scène sombre n'atteint jamais les
caractères denses, une scène claire jamais les caractères clairsemés. Les
niveaux automatiques étirent chaque image sur toute la plage, et le gamma
remodèle les tons moyens, là où une rampe de caractères porte le plus de détail.
"""

from __future__ import annotations

from typing import Any

# On passe par des percentiles plutôt que par les vrais minimum et maximum, pour
# que quelques pixels isolés ne définissent pas toute la plage.
DEFAULT_LOW_PERCENTILE = 2.0
DEFAULT_HIGH_PERCENTILE = 98.0

# Les niveaux glissent progressivement vers leur nouvelle valeur, pour que la
# lecture ne pulse pas quand un objet lumineux traverse le cadre.
DEFAULT_LEVEL_INERTIA = 0.15

# En dessous de cet écart, l'image est considérée comme plate et laissée telle
# quelle, ce qui évite d'amplifier le bruit du capteur sur un plan presque noir.
_MINIMUM_SPREAD = 8.0


def apply_gamma(brightness: Any, gamma: float, np: Any) -> Any:
    """Remodèle les tons moyens. Au-dessus de 1 ça éclaircit, en dessous ça assombrit."""
    if gamma == 1.0:
        return brightness
    normalized = np.clip(brightness, 0.0, 255.0) / 255.0
    return np.power(normalized, 1.0 / gamma) * 255.0


class ToneMapper:
    """Étire la luminosité sur toute la rampe, de façon stable d'une image à l'autre."""

    __slots__ = ("gamma", "auto_levels", "low_percentile", "high_percentile", "inertia", "_low", "_high")

    def __init__(
        self,
        *,
        gamma: float = 1.0,
        auto_levels: bool = False,
        low_percentile: float = DEFAULT_LOW_PERCENTILE,
        high_percentile: float = DEFAULT_HIGH_PERCENTILE,
        inertia: float = DEFAULT_LEVEL_INERTIA,
    ) -> None:
        if not 0.0 <= low_percentile < high_percentile <= 100.0:
            raise ValueError("Les percentiles doivent vérifier 0 <= bas < haut <= 100.")
        if not 0.0 < inertia <= 1.0:
            raise ValueError("L'inertie des niveaux doit être comprise entre 0 et 1.")
        self.gamma = gamma
        self.auto_levels = auto_levels
        self.low_percentile = low_percentile
        self.high_percentile = high_percentile
        self.inertia = inertia
        self._low: float | None = None
        self._high: float | None = None

    @property
    def active(self) -> bool:
        return self.auto_levels or self.gamma != 1.0

    def reset(self) -> None:
        """Oublie les niveaux lissés, lors d'un saut ou d'un redémarrage de boucle."""
        self._low = None
        self._high = None

    def _levels(self, brightness: Any, np: Any) -> tuple[float, float]:
        low = float(np.percentile(brightness, self.low_percentile))
        high = float(np.percentile(brightness, self.high_percentile))
        if high - low < _MINIMUM_SPREAD:
            low, high = 0.0, 255.0

        if self._low is None or self._high is None:
            self._low, self._high = low, high
        else:
            self._low += (low - self._low) * self.inertia
            self._high += (high - self._high) * self.inertia
        return self._low, self._high

    def apply(self, brightness: Any, np: Any) -> Any:
        """Renvoie un tableau de luminosité étiré et corrigé en gamma, à la place de l'entrée."""
        result = brightness
        if self.auto_levels:
            low, high = self._levels(result, np)
            spread = high - low
            if spread >= _MINIMUM_SPREAD:
                result = (result - low) * (255.0 / spread)
                result = np.clip(result, 0.0, 255.0)
        return apply_gamma(result, self.gamma, np)
