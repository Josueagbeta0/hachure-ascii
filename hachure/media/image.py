"""Conversion d'une image fixe en ASCII."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hachure.render import RenderStyle, render_array
from hachure.tone import ToneMapper


class ImageRenderError(RuntimeError):
    pass


def _load_pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageRenderError(
            "Le rendu d'image exige Pillow. Installez d'abord les dépendances du projet."
        ) from exc
    return Image


def _load_numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise ImageRenderError(
            "Le rendu d'image exige NumPy. Installez d'abord les dépendances du projet."
        ) from exc
    return numpy


def get_image_dimensions(path: Path) -> tuple[int, int]:
    Image = _load_pillow()
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError) as exc:
        raise ImageRenderError(f"Impossible d'ouvrir l'image '{path}' : {exc}") from exc


def render_image(
    path: Path,
    *,
    width: int,
    height: int,
    style: RenderStyle,
    crop: tuple[int, int, int, int] | None = None,
    tone: ToneMapper | None = None,
) -> str:
    """Rend un fichier image sous forme de texte de terminal.

    ``crop`` est une région ``(largeur, hauteur, x, y)`` appliquée avant la mise
    à l'échelle : c'est ainsi que le mode d'ajustement ``cover`` remplit la grille.
    """
    Image = _load_pillow()
    np = _load_numpy()

    if not path.is_file():
        raise ImageRenderError(f"Image introuvable : {path}")

    target_cols = style.pixel_cols(width)
    target_rows = style.pixel_rows(height)
    mode = "RGB" if style.colored else "L"

    try:
        with Image.open(path) as source:
            converted = source.convert(mode)
            if crop is not None:
                crop_width, crop_height, offset_x, offset_y = crop
                converted = converted.crop(
                    (
                        offset_x,
                        offset_y,
                        offset_x + crop_width,
                        offset_y + crop_height,
                    )
                )
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            resized = converted.resize((target_cols, target_rows), resampling)
            array = np.asarray(resized, dtype=np.float32)
    except (OSError, ValueError) as exc:
        raise ImageRenderError(f"Impossible de rendre l'image '{path}' : {exc}") from exc

    if style.colored and array.ndim != 3:
        raise ImageRenderError(f"Impossible de lire les canaux de couleur de '{path}'.")

    return render_array(array, style, np, tone=tone)
