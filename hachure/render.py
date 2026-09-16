"""Conversion commune des tableaux de pixels en images de terminal.

Les chaînes image fixe et vidéo font toutes deux passer leurs tableaux NumPy par
ici, de sorte que couleur, géométrie de cellule, tonalité et fabrication des
codes d'échappement restent au même endroit.

Deux géométries de cellule sont gérées :

``char``
    Une cellule de terminal porte un pixel source. La luminosité choisit un
    caractère de la rampe. Avec ``edges`` activé, la source est échantillonnée
    au-dessus de la résolution des cellules, pour que le contour dominant de
    chaque cellule puisse remplacer ce caractère par un glyphe de ligne adapté.

``half``
    Une cellule de terminal porte deux pixels empilés verticalement, dessinés
    avec le demi-bloc supérieur. Le premier plan peint le pixel du haut et
    l'arrière-plan celui du bas, ce qui double la résolution verticale utile au
    prix d'un rendu qui ne ressemble plus à des caractères.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from hachure.color import RESET, AnsiPalette, ColorDepth
from hachure.edges import EDGE_GLYPHS, block_mean, edge_indices
from hachure.tone import ToneMapper

CellMode = Literal["char", "half"]

CELL_MODES: tuple[CellMode, ...] = ("char", "half")

UPPER_HALF_BLOCK = "▀"
LOWER_HALF_BLOCK = "▄"

# Nombre de pixels source échantillonnés par côté de cellule quand les contours
# sont activés. Trois suffit à une orientation stable sans tripler le coût de
# décodage.
EDGE_SUPERSAMPLE = 3

# Au-delà de cet écart haut/bas, une demi-cellule monochrome affiche une arête
# de bloc au lieu de moyenner les deux pixels en un seul caractère de rampe.
_MONO_SPLIT_THRESHOLD = 40.0


@dataclass(frozen=True)
class RenderStyle:
    """Tout ce qu'il faut pour transformer un tableau de pixels en texte de terminal."""

    ramp: str
    cell_mode: CellMode = "char"
    color_depth: ColorDepth = "none"
    quantization: int = 4
    edges: bool = False
    edge_strength: float = 0.5

    @property
    def rows_per_cell(self) -> int:
        return 2 if self.cell_mode == "half" else 1

    @property
    def colored(self) -> bool:
        return self.color_depth != "none"

    @property
    def edges_active(self) -> bool:
        """Les glyphes de contour n'ont de sens que là où un glyphe est réellement choisi."""
        return self.edges and self.cell_mode == "char"

    @property
    def supersample(self) -> int:
        return EDGE_SUPERSAMPLE if self.edges_active else 1

    @property
    def alphabet(self) -> str:
        """La rampe, suivie des glyphes de contour quand ceux-ci entrent en jeu."""
        return self.ramp + "".join(EDGE_GLYPHS) if self.edges_active else self.ramp

    def pixel_rows(self, rows: int) -> int:
        """Nombre de lignes de balayage source nécessaires pour une grille de ``rows`` cellules."""
        return rows * self.rows_per_cell * self.supersample

    def pixel_cols(self, cols: int) -> int:
        """Nombre de colonnes source nécessaires pour une grille de ``cols`` cellules."""
        return cols * self.supersample

    def palette(self) -> AnsiPalette:
        return AnsiPalette(self.color_depth)


def _luminance(array: Any, np: Any) -> Any:
    return 0.299 * array[..., 0] + 0.587 * array[..., 1] + 0.114 * array[..., 2]


def _brightness(array: Any, np: Any) -> Any:
    return _luminance(array, np) if array.ndim == 3 else array


def _ramp_indices(brightness: Any, ramp: str, np: Any) -> Any:
    return np.clip(
        (brightness * (len(ramp) - 1) / 255.0).astype(np.int32), 0, len(ramp) - 1
    )


def _apply_tone(array: Any, tone: ToneMapper | None, np: Any) -> Any:
    """Met la luminosité en forme, en préservant la teinte des entrées couleur par mise à l'échelle de tous les canaux."""
    if tone is None or not tone.active:
        return array
    if array.ndim != 3:
        return tone.apply(array, np)
    brightness = _luminance(array, np)
    shaped = tone.apply(brightness, np)
    with np.errstate(invalid="ignore", divide="ignore"):
        gain = np.where(brightness > 1.0, shaped / np.maximum(brightness, 1e-3), 1.0)
    return np.clip(array * gain[..., None], 0.0, 255.0)


def _quantize(array: Any, step: int, np: Any) -> Any:
    clipped = np.clip(array, 0, 255)
    if step > 1:
        return (clipped.astype(np.int32) // step * step).astype(np.int32)
    return clipped.astype(np.int32)


def _pack_rgb(colors: Any, np: Any) -> Any:
    return (
        (colors[..., 0].astype(np.int64) << 16)
        | (colors[..., 1].astype(np.int64) << 8)
        | colors[..., 2].astype(np.int64)
    )


def _row_runs(keys: Any, np: Any) -> tuple[list[int], list[int]]:
    """Renvoie les décalages de début et de fin des plages sur une grille aplatie, découpées par ligne.

    Une plage ne chevauche jamais une frontière de ligne : chaque ligne rendue
    reste ainsi autonome, et donc redessinable seule.
    """
    rows, cols = keys.shape
    flat = keys.reshape(-1)
    changes = np.flatnonzero(flat[1:] != flat[:-1]) + 1
    if rows > 1:
        row_starts = np.arange(cols, rows * cols, cols)
        boundaries = np.union1d(changes, row_starts)
    else:
        boundaries = changes
    starts = np.concatenate((np.zeros(1, dtype=boundaries.dtype), boundaries))
    ends = np.concatenate((boundaries, np.full(1, flat.size, dtype=boundaries.dtype)))
    return starts.tolist(), ends.tolist()


def _char_cells(
    array: Any, style: RenderStyle, tone: ToneMapper | None, np: Any
) -> tuple[Any, Any]:
    """Réduit un tableau source en codes de glyphe par cellule et, en couleur, en couleurs de cellule.

    Les codes de glyphe indexent :attr:`RenderStyle.alphabet` : les glyphes de
    contour se placent simplement après la fin de la rampe, et tout l'aval reste
    uniforme.
    """
    scale = style.supersample
    source_brightness = _brightness(array, np) if style.edges_active else None

    cells = block_mean(array, scale, scale, np) if scale > 1 else array
    cells = _apply_tone(cells, tone, np)
    brightness = _brightness(cells, np)
    codes = _ramp_indices(brightness, style.ramp, np)

    if style.edges_active and source_brightness is not None:
        mask, orientation = edge_indices(
            source_brightness, scale, scale, np, strength=style.edge_strength
        )
        codes = np.where(mask, orientation + len(style.ramp), codes)

    colors = cells if style.colored else None
    return codes, colors


def _emit_mono(codes: Any, alphabet: str, np: Any) -> str:
    glyphs = np.array(list(alphabet), dtype="<U1")[codes]
    return "\n".join("".join(row) for row in glyphs.tolist())


def _emit_color(
    codes: Any,
    colors: Any,
    style: RenderStyle,
    palette: AnsiPalette,
    np: Any,
) -> str:
    alphabet = style.alphabet
    quantized = _quantize(colors, style.quantization, np)
    packed = _pack_rgb(quantized, np)

    keys = (packed << 8) | codes.astype(np.int64)
    starts, ends = _row_runs(keys, np)

    flat_packed = packed.reshape(-1).tolist()
    flat_codes = codes.reshape(-1).tolist()
    cols = codes.shape[1]
    foreground = palette.foreground

    parts: list[str] = []
    current_row = 0
    last_color = -1
    for start, end in zip(starts, ends):
        row = start // cols
        if row != current_row:
            parts.append(RESET)
            parts.append("\n" * (row - current_row))
            current_row = row
            last_color = -1
        color = flat_packed[start]
        if color != last_color:
            parts.append(foreground(color))
            last_color = color
        parts.append(alphabet[flat_codes[start]] * (end - start))
    parts.append(RESET)
    return "".join(parts)


def _render_mono_half(
    array: Any, style: RenderStyle, tone: ToneMapper | None, np: Any
) -> str:
    """Dessine deux lignes de balayage par cellule sans couleur, avec des glyphes de bloc pour les arêtes."""
    brightness = _apply_tone(_brightness(array, np), tone, np)
    top = brightness[0::2]
    bottom = brightness[1::2]
    average = (top + bottom) * 0.5
    indices = _ramp_indices(average, style.ramp, np)

    difference = top - bottom
    split = np.abs(difference) > _MONO_SPLIT_THRESHOLD
    upper = split & (difference > 0)
    lower = split & (difference <= 0)

    glyphs = np.array(list(style.ramp), dtype="<U1")[indices]
    glyphs = np.where(upper, UPPER_HALF_BLOCK, glyphs)
    glyphs = np.where(lower, LOWER_HALF_BLOCK, glyphs)
    return "\n".join("".join(row) for row in glyphs.tolist())


def _render_color_half(
    array: Any,
    style: RenderStyle,
    palette: AnsiPalette,
    tone: ToneMapper | None,
    np: Any,
) -> str:
    shaped = _apply_tone(array, tone, np)
    colors = _quantize(shaped, style.quantization, np)
    top = _pack_rgb(colors[0::2], np)
    bottom = _pack_rgb(colors[1::2], np)

    keys = (top << 24) | bottom
    starts, ends = _row_runs(keys, np)

    flat_top = top.reshape(-1).tolist()
    flat_bottom = bottom.reshape(-1).tolist()
    cols = top.shape[1]
    pair = palette.pair

    parts: list[str] = []
    current_row = 0
    last_key = -1
    for start, end in zip(starts, ends):
        row = start // cols
        if row != current_row:
            parts.append(RESET)
            parts.append("\n" * (row - current_row))
            current_row = row
            last_key = -1
        key = (flat_top[start] << 24) | flat_bottom[start]
        if key != last_key:
            parts.append(pair(flat_top[start], flat_bottom[start]))
            last_key = key
        parts.append(UPPER_HALF_BLOCK * (end - start))
    parts.append(RESET)
    return "".join(parts)


def render_array(
    array: Any,
    style: RenderStyle,
    np: Any,
    *,
    palette: AnsiPalette | None = None,
    tone: ToneMapper | None = None,
) -> str:
    """Rend un tableau de pixels sous forme de texte de terminal.

    ``array`` est de forme ``(lignes, colonnes)`` pour les sources monochromes et
    ``(lignes, colonnes, 3)`` pour les sources couleur, dimensionné par
    :meth:`RenderStyle.pixel_rows` et :meth:`RenderStyle.pixel_cols`.
    """
    if style.colored and array.ndim != 3:
        raise ValueError("Le rendu en couleur exige un tableau RVB.")

    if style.cell_mode == "half":
        if style.colored:
            active = palette if palette is not None else style.palette()
            return _render_color_half(array, style, active, tone, np)
        return _render_mono_half(array, style, tone, np)

    codes, colors = _char_cells(array, style, tone, np)
    if style.colored:
        active = palette if palette is not None else style.palette()
        return _emit_color(codes, colors, style, active, np)
    return _emit_mono(codes, style.alphabet, np)
