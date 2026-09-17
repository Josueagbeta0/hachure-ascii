"""Conversion d'une image fixe en ASCII."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hachure.i18n import T
from hachure.render import RenderStyle, render_array
from hachure.tone import ToneMapper


class ImageRenderError(RuntimeError):
    pass


def _load_pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageRenderError(T("erreur.image_pillow")) from exc
    return Image


def _load_numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise ImageRenderError(T("erreur.image_numpy")) from exc
    return numpy


def get_image_dimensions(path: Path) -> tuple[int, int]:
    Image = _load_pillow()
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError) as exc:
        raise ImageRenderError(T("erreur.image_ouverture", chemin=path, cause=exc)) from exc


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
        raise ImageRenderError(T("erreur.image_introuvable", chemin=path))

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
        raise ImageRenderError(T("erreur.image_rendu", chemin=path, cause=exc)) from exc

    if style.colored and array.ndim != 3:
        raise ImageRenderError(T("erreur.image_canaux", chemin=path))

    return render_array(array, style, np, tone=tone)
