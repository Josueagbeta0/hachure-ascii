"""Sélection de glyphes attentive à la structure.

Choisir un caractère à partir de la seule luminosité gâche ce qu'une grille de
caractères sait le mieux faire : la forme. Ce module échantillonne la source
au-dessus de la résolution des cellules, mesure l'orientation de contour
dominante dans chaque cellule via un tenseur de structure, et remplace le
caractère de luminosité par un glyphe de ligne partout où un contour réel et
cohérent la traverse.

On utilise le tenseur de structure plutôt qu'un simple gradient moyenné parce
que des gradients opposés le long d'un même contour s'annulent à la moyenne —
exactement ce qui se produit dans une cellule à cheval sur une ligne fine.
"""

from __future__ import annotations

import math
from typing import Any

# Ordonnés pour qu'un index corresponde directement à une classe d'orientation.
EDGE_GLYPHS: tuple[str, ...] = ("-", "\\", "|", "/")

# Un contour doit atteindre cette force, relative à l'énergie de gradient de
# l'image elle-même, pour supplanter le caractère de luminosité.
DEFAULT_STRENGTH = 0.5

# À quel point la structure locale doit être directionnelle, de 0 (n'importe
# laquelle) à 1 (une droite parfaite). En dessous, la cellule est une texture,
# pas un contour.
_MINIMUM_COHERENCE = 0.35

_BUCKET_WIDTH = math.pi / 4.0


def _sobel(luminance: Any, np: Any) -> tuple[Any, Any]:
    """Renvoie les gradients horizontal et vertical, bords compris via un remplissage par duplication."""
    padded = np.pad(luminance, 1, mode="edge")
    north_west = padded[:-2, :-2]
    north = padded[:-2, 1:-1]
    north_east = padded[:-2, 2:]
    west = padded[1:-1, :-2]
    east = padded[1:-1, 2:]
    south_west = padded[2:, :-2]
    south = padded[2:, 1:-1]
    south_east = padded[2:, 2:]

    gradient_x = (north_east + 2.0 * east + south_east) - (
        north_west + 2.0 * west + south_west
    )
    gradient_y = (south_west + 2.0 * south + south_east) - (
        north_west + 2.0 * north + north_east
    )
    return gradient_x, gradient_y


def _block_sum(array: Any, block_rows: int, block_cols: int, np: Any) -> Any:
    rows = array.shape[0] // block_rows
    cols = array.shape[1] // block_cols
    trimmed = array[: rows * block_rows, : cols * block_cols]
    return trimmed.reshape(rows, block_rows, cols, block_cols).sum(axis=(1, 3))


def block_mean(array: Any, block_rows: int, block_cols: int, np: Any) -> Any:
    """Réduit chaque tuile ``block_rows`` x ``block_cols`` à une seule valeur moyenne."""
    if block_rows == 1 and block_cols == 1:
        return array
    rows = array.shape[0] // block_rows
    cols = array.shape[1] // block_cols
    trimmed = array[: rows * block_rows, : cols * block_cols]
    if array.ndim == 3:
        reshaped = trimmed.reshape(rows, block_rows, cols, block_cols, array.shape[2])
        return reshaped.mean(axis=(1, 3))
    return trimmed.reshape(rows, block_rows, cols, block_cols).mean(axis=(1, 3))


def edge_indices(
    luminance: Any,
    block_rows: int,
    block_cols: int,
    np: Any,
    *,
    strength: float = DEFAULT_STRENGTH,
) -> tuple[Any, Any]:
    """Trouve les cellules contenant un contour, et le glyphe qui épouse sa direction.

    Renvoie ``(masque, indices)`` sur la grille de cellules, où ``indices``
    sélectionne dans :data:`EDGE_GLYPHS`.
    """
    gradient_x, gradient_y = _sobel(luminance, np)

    # Tenseur de structure, accumulé sur chaque cellule.
    tensor_xx = _block_sum(gradient_x * gradient_x, block_rows, block_cols, np)
    tensor_yy = _block_sum(gradient_y * gradient_y, block_rows, block_cols, np)
    tensor_xy = _block_sum(gradient_x * gradient_y, block_rows, block_cols, np)

    trace = tensor_xx + tensor_yy
    difference = tensor_xx - tensor_yy
    spread = np.sqrt(difference * difference + 4.0 * tensor_xy * tensor_xy)

    with np.errstate(invalid="ignore", divide="ignore"):
        coherence = np.where(trace > 0, spread / trace, 0.0)

    energy = np.sqrt(np.maximum(trace, 0.0))
    ceiling = float(np.percentile(energy, 97.0))
    if ceiling <= 0.0:
        return np.zeros(trace.shape, dtype=bool), np.zeros(trace.shape, dtype=np.int32)

    mask = (energy >= ceiling * strength) & (coherence >= _MINIMUM_COHERENCE)

    # Direction dominante du gradient, puis le contour lui-même, perpendiculaire.
    gradient_angle = 0.5 * np.arctan2(2.0 * tensor_xy, difference)
    edge_angle = gradient_angle + math.pi / 2.0
    normalized = np.mod(edge_angle + _BUCKET_WIDTH / 2.0, math.pi)
    indices = np.clip(
        (normalized / _BUCKET_WIDTH).astype(np.int32), 0, len(EDGE_GLYPHS) - 1
    )
    return mask, indices
