"""Rampes luminosité-vers-caractère partagées, et les outils pour les calibrer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from hachure.i18n import T

CHARSETS = {
    "classic": " .:-=+*#%@",
    "detailed": " .`^\\,:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "letters": ".,:;irsXA253hMHGS#9B&@",
    # Mesurée sur Cascadia Mono avec `hachure calibrate` : pas réguliers en
    # couverture d'encre réelle, biaisée vers les glyphes dont l'encre est
    # répartie sur toute la cellule, et sans les quatre glyphes de ligne
    # réservés à l'orientation des contours.
    "smooth": " :;!?c7S58B@",
}

DEFAULT_CHARSET = "classic"

# Glyphes candidats à la calibration : l'ASCII imprimable moins l'espace, qui
# occupe toujours l'extrémité vide d'une rampe ; moins les caractères assez
# éloignés de la ligne de base pour se lire comme du bruit plutôt que comme un
# ton ; et moins les quatre glyphes de ligne, réservés à l'orientation des
# contours et qui doivent rester sans ambiguïté.
_CALIBRATION_EXCLUDED = "`'\",._^~-|/\\"

_CALIBRATION_TILES = 3


def get_charset(name: str = DEFAULT_CHARSET, *, invert: bool = False) -> str:
    """Renvoie une rampe de caractères nommée, du sombre vers le clair."""
    try:
        ramp = CHARSETS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(CHARSETS))
        raise ValueError(T("erreur.charset_inconnu", nom=name, choix=choices)) from exc
    return ramp[::-1] if invert else ramp


def brightness_to_index(brightness: float, ramp_length: int) -> int:
    """Convertit une luminosité de 0..255 en un index de rampe toujours valide."""
    if ramp_length < 1:
        raise ValueError(T("erreur.rampe_vide"))
    value = max(0.0, min(255.0, float(brightness)))
    return int(value * (ramp_length - 1) / 255.0)


def brightness_to_char(brightness: float, ramp: str) -> str:
    return ramp[brightness_to_index(brightness, len(ramp))]


def candidate_characters() -> str:
    """L'ASCII imprimable digne d'être mesuré, dans l'ordre des points de code."""
    return "".join(
        character
        for code in range(0x21, 0x7F)
        if (character := chr(code)) not in _CALIBRATION_EXCLUDED
    )


def measure_glyphs(
    font_path: Path, *, size: int = 32, characters: str | None = None
) -> dict[str, tuple[float, float]]:
    """Mesure la couverture d'encre de chaque glyphe et la régularité de sa répartition.

    Renvoie ``{caractère: (couverture, uniformité)}``, les deux dans ``0..1``.
    La couverture est le critère de tri d'une rampe ; l'uniformité est ce qui
    distingue un glyphe lu comme un aplat de ton d'un glyphe lu comme une marque.
    """
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(font_path), size)
    ascent, descent = font.getmetrics()
    cell_height = max(1, ascent + descent)
    cell_width = max(1, round(font.getlength("M")))

    results: dict[str, tuple[float, float]] = {}
    for character in characters if characters is not None else candidate_characters():
        image = Image.new("L", (cell_width, cell_height), 0)
        ImageDraw.Draw(image).text((0, 0), character, font=font, fill=255)
        pixels = image.load()

        total = 0.0
        tiles: list[float] = []
        tile_height = max(1, cell_height // _CALIBRATION_TILES)
        tile_width = max(1, cell_width // _CALIBRATION_TILES)
        for tile_y in range(_CALIBRATION_TILES):
            for tile_x in range(_CALIBRATION_TILES):
                ink = 0.0
                count = 0
                for y in range(tile_y * tile_height, min((tile_y + 1) * tile_height, cell_height)):
                    for x in range(tile_x * tile_width, min((tile_x + 1) * tile_width, cell_width)):
                        ink += pixels[x, y]
                        count += 1
                if count:
                    tiles.append(ink / (count * 255.0))
                total += ink

        coverage = total / (cell_width * cell_height * 255.0)
        if tiles:
            mean = sum(tiles) / len(tiles)
            variance = sum((value - mean) ** 2 for value in tiles) / len(tiles)
            spread = variance**0.5
            uniformity = 1.0 - min(1.0, spread / mean) if mean > 0 else 0.0
        else:
            uniformity = 0.0
        results[character] = (coverage, uniformity)
    return results


def build_ramp(
    measurements: dict[str, tuple[float, float]],
    *,
    length: int = 12,
    uniformity_weight: float = 1.0,
) -> str:
    """Choisit une rampe dont les pas sont régulièrement espacés en couverture d'encre réelle.

    Chaque pas vise une fraction régulière de la plage de couverture mesurée ;
    parmi les glyphes proches de cette cible, celui dont l'encre est la mieux
    répartie l'emporte.
    """
    if length < 2:
        raise ValueError(T("erreur.rampe_deux"))
    if not measurements:
        raise ValueError(T("erreur.mesures_absentes"))

    ordered = sorted(measurements.items(), key=lambda item: item[1][0])
    lightest = ordered[0][1][0]
    heaviest = ordered[-1][1][0]
    if heaviest <= lightest:
        raise ValueError(T("erreur.couverture_plate"))

    span = heaviest - lightest
    # Les glyphes à cette distance de la cible sont considérés comme
    # interchangeables : le départage se fait alors sur la régularité de
    # répartition de leur encre.
    window = span / (2.0 * (length - 1))

    ramp = [" "]
    used = {" "}
    previous_coverage = 0.0

    for step in range(1, length):
        target = lightest + span * (step - 1) / (length - 2) if length > 2 else heaviest
        available = [
            (character, coverage, uniformity)
            for character, (coverage, uniformity) in ordered
            if character not in used and coverage >= previous_coverage
        ]
        if not available:
            break

        near = [entry for entry in available if abs(entry[1] - target) <= window]
        if near:
            character, coverage, _ = max(
                near,
                key=lambda entry: entry[2] * uniformity_weight
                - abs(entry[1] - target) / span,
            )
        else:
            character, coverage, _ = min(available, key=lambda entry: abs(entry[1] - target))

        ramp.append(character)
        used.add(character)
        previous_coverage = coverage

    return "".join(ramp)


def calibrate(font_path: Path, *, size: int = 32, length: int = 12) -> str:
    """Mesure une police et renvoie une rampe calibrée pour elle."""
    return build_ramp(measure_glyphs(font_path, size=size), length=length)


def find_monospace_font(candidates: Iterable[Path] | None = None) -> Path | None:
    """Localise une police à chasse fixe sur laquelle se calibrer."""
    search: tuple[Path, ...]
    if candidates is not None:
        search = tuple(candidates)
    else:
        search = (
            Path("C:/Windows/Fonts/CascadiaMono.ttf"),
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("C:/Windows/Fonts/lucon.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSansMono.ttf"),
            Path("/System/Library/Fonts/Menlo.ttc"),
        )
    for candidate in search:
        if candidate.is_file():
            return candidate
    return None
