"""Détection de la profondeur de couleur du terminal et fabrication des codes ANSI."""

from __future__ import annotations

import os
import sys
from typing import Final, Literal

ColorDepth = Literal["none", "ansi256", "truecolor"]

COLOR_DEPTHS: Final[tuple[ColorDepth, ...]] = ("none", "ansi256", "truecolor")

RESET: Final = "\033[0m"

# Les valeurs décimales des canaux sont formatées une fois, pas à chaque cellule.
_CHANNEL_TEXT: Final[tuple[str, ...]] = tuple(str(value) for value in range(256))

# Le cube 6x6x6 d'xterm-256 commence à l'index 16 ; la rampe de gris à 232.
_CUBE_LEVELS: Final[tuple[int, ...]] = (0, 95, 135, 175, 215, 255)

_PREFIX_CACHE_LIMIT: Final = 1 << 16


def detect_color_depth(stream=None) -> ColorDepth:
    """Déduit ce que le terminal courant sait afficher."""
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return "none"
    if not getattr(stream, "isatty", lambda: False)():
        return "none"

    colorterm = os.environ.get("COLORTERM", "").lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        return "truecolor"

    term = os.environ.get("TERM", "").lower()
    if "truecolor" in term or "direct" in term:
        return "truecolor"

    # Windows Terminal, le conhost moderne et VS Code gèrent tous la couleur 24 bits.
    if os.name == "nt" and (
        os.environ.get("WT_SESSION")
        or os.environ.get("TERM_PROGRAM") == "vscode"
        or not term
    ):
        return "truecolor"

    if "256" in term:
        return "ansi256"
    if term in ("dumb", ""):
        return "none"
    return "ansi256"


def _cube_index(value: int) -> int:
    best = 0
    best_distance = 1024
    for index, level in enumerate(_CUBE_LEVELS):
        distance = abs(level - value)
        if distance < best_distance:
            best_distance = distance
            best = index
    return best


def rgb_to_ansi256(red: int, green: int, blue: int) -> int:
    """Associe un triplet RVB à l'entrée de palette xterm-256 la plus proche."""
    if abs(red - green) < 8 and abs(green - blue) < 8:
        gray = (red + green + blue) // 3
        if gray < 8:
            return 16
        if gray > 246:
            return 231
        return 232 + (gray - 8) * 24 // 239
    return (
        16
        + 36 * _cube_index(red)
        + 6 * _cube_index(green)
        + _cube_index(blue)
    )


class AnsiPalette:
    """Construit et mémoïse les préfixes d'échappement pour une profondeur de couleur."""

    __slots__ = ("depth", "_foreground", "_background", "_pair")

    def __init__(self, depth: ColorDepth) -> None:
        self.depth = depth
        self._foreground: dict[int, str] = {}
        self._background: dict[int, str] = {}
        self._pair: dict[int, str] = {}

    @staticmethod
    def pack(red: int, green: int, blue: int) -> int:
        return (red << 16) | (green << 8) | blue

    def _evict(self, cache: dict[int, str]) -> None:
        if len(cache) > _PREFIX_CACHE_LIMIT:
            cache.clear()

    def foreground(self, packed: int) -> str:
        """Renvoie la séquence d'échappement qui fixe le premier plan à une valeur RVB compactée."""
        try:
            return self._foreground[packed]
        except KeyError:
            pass
        red, green, blue = (packed >> 16) & 255, (packed >> 8) & 255, packed & 255
        if self.depth == "truecolor":
            code = (
                "\033[38;2;"
                + _CHANNEL_TEXT[red]
                + ";"
                + _CHANNEL_TEXT[green]
                + ";"
                + _CHANNEL_TEXT[blue]
                + "m"
            )
        elif self.depth == "ansi256":
            code = "\033[38;5;" + _CHANNEL_TEXT[rgb_to_ansi256(red, green, blue)] + "m"
        else:
            code = ""
        self._evict(self._foreground)
        self._foreground[packed] = code
        return code

    def background(self, packed: int) -> str:
        try:
            return self._background[packed]
        except KeyError:
            pass
        red, green, blue = (packed >> 16) & 255, (packed >> 8) & 255, packed & 255
        if self.depth == "truecolor":
            code = (
                "\033[48;2;"
                + _CHANNEL_TEXT[red]
                + ";"
                + _CHANNEL_TEXT[green]
                + ";"
                + _CHANNEL_TEXT[blue]
                + "m"
            )
        elif self.depth == "ansi256":
            code = "\033[48;5;" + _CHANNEL_TEXT[rgb_to_ansi256(red, green, blue)] + "m"
        else:
            code = ""
        self._evict(self._background)
        self._background[packed] = code
        return code

    def pair(self, packed_foreground: int, packed_background: int) -> str:
        """Renvoie une séquence combinée premier plan + arrière-plan, pour les cellules demi-bloc."""
        key = (packed_foreground << 24) | packed_background
        try:
            return self._pair[key]
        except KeyError:
            pass
        code = self.foreground(packed_foreground) + self.background(packed_background)
        self._evict(self._pair)
        self._pair[key] = code
        return code
