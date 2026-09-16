"""Dimensionnement du terminal, affichage, et gestion du cycle de vie des animations."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import time
from collections.abc import Callable, Iterator
from typing import Literal

CHAR_ASPECT = 0.5

CHAR_ASPECT_ENV = "HACHURE_CHAR_ASPECT"

FitMode = Literal["contain", "cover"]

FIT_MODES: tuple[FitMode, ...] = ("contain", "cover")

# Le terminal n'est mesuré que toutes les quelques images ; l'appel est peu coûteux, pas gratuit.
_RESIZE_POLL_FRAMES = 10


def default_char_aspect() -> float:
    """Largeur d'une cellule divisée par sa hauteur, surchargeable pour les polices atypiques."""
    raw = os.environ.get(CHAR_ASPECT_ENV)
    if not raw:
        return CHAR_ASPECT
    try:
        value = float(raw)
    except ValueError:
        return CHAR_ASPECT
    return value if 0.1 <= value <= 2.0 else CHAR_ASPECT


def terminal_size(fallback: tuple[int, int] = (120, 40)) -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=fallback)
    return size.columns, size.lines


def fit_source_size(
    source_width: int,
    source_height: int,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
    available: tuple[int, int] | None = None,
    char_aspect: float | None = None,
    fit: FitMode = "contain",
) -> tuple[int, int]:
    """Insère un média source dans le terminal en préservant son rapport visuel.

    Avec ``fit="cover"``, la grille remplit plutôt toute la zone disponible, et
    la source est censée être recadrée en conséquence ; voir :func:`source_crop`.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Les dimensions de la source doivent être positives.")
    aspect = default_char_aspect() if char_aspect is None else char_aspect
    if aspect <= 0:
        raise ValueError("La correction de rapport des caractères doit être positive.")

    term_cols, term_rows = available or terminal_size()
    cols = max(1, term_cols - 2)
    rows_limit = max(1, term_rows - 2)

    if max_width is not None:
        cols = min(cols, max_width)
    if max_height is not None:
        rows_limit = min(rows_limit, max_height)

    if fit == "cover":
        return cols, rows_limit

    source_ratio = source_height / source_width
    rows = max(1, round(cols * source_ratio * aspect))

    if rows > rows_limit:
        rows = rows_limit
        cols = max(1, round(rows / (source_ratio * aspect)))

    return cols, rows


def source_crop(
    source_width: int,
    source_height: int,
    cols: int,
    rows: int,
    *,
    char_aspect: float | None = None,
) -> tuple[int, int, int, int]:
    """Renvoie le recadrage centré ``(largeur, hauteur, x, y)`` qui remplit une grille.

    La région conserve le rapport d'image que la grille de caractères affichera :
    un plan en portrait perd son haut et son bas plutôt que d'être encadré de
    bandes noires.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Les dimensions de la source doivent être positives.")
    if cols <= 0 or rows <= 0:
        raise ValueError("Les dimensions de la grille doivent être positives.")
    aspect = default_char_aspect() if char_aspect is None else char_aspect

    target_ratio = cols * aspect / rows
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = max(1, round(source_height * target_ratio))
    else:
        crop_width = source_width
        crop_height = max(1, round(source_width / target_ratio))

    crop_width = min(crop_width, source_width)
    crop_height = min(crop_height, source_height)
    offset_x = (source_width - crop_width) // 2
    offset_y = (source_height - crop_height) // 2
    return crop_width, crop_height, offset_x, offset_y


def fit_demo_size(
    *,
    default_width: int,
    height_ratio: float,
    width: int | None = None,
    height: int | None = None,
    available: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Choisit une grille de caractères compatible avec le terminal pour une démo procédurale."""
    if height_ratio <= 0:
        raise ValueError("Le rapport de hauteur doit être positif.")
    term_cols, term_rows = available or terminal_size()
    cols = min(width or default_width, max(1, term_cols - 2))
    rows = height or max(1, round(cols * height_ratio))

    if rows > max(1, term_rows - 1):
        rows = max(1, term_rows - 1)
        if height is None:
            cols = min(cols, max(1, round(rows / height_ratio)))

    return cols, rows


def enable_windows_ansi() -> None:
    """Active le traitement de terminal virtuel sans lancer de shell."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if handle in (0, -1):
            raise OSError("aucun handle de console")
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError("échec de GetConsoleMode")
        enable_virtual_terminal_processing = 0x0004
        kernel32.SetConsoleMode(
            handle, mode.value | enable_virtual_terminal_processing
        )
    except (ImportError, OSError, AttributeError):
        # Repli sur l'astuce du shell, qui a le même effet de bord.
        os.system("")


def use_utf8_output() -> None:
    """S'assure que les glyphes de bloc survivent à la page de codes par défaut de la console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


class Screen:
    """Tampon d'image adressé au curseur, qui ne repeint que les lignes modifiées."""

    __slots__ = ("_previous", "_size")

    def __init__(self) -> None:
        self._previous: list[str] = []
        self._size: tuple[int, int] | None = None

    def invalidate(self) -> None:
        """Force le prochain affichage à tout repeindre."""
        self._previous = []

    def draw(self, frame: str) -> None:
        lines = frame.split("\n")
        size = terminal_size()
        if size != self._size:
            self._size = size
            self.invalidate()

        previous = self._previous
        parts: list[str] = []
        for index, line in enumerate(lines):
            if index < len(previous) and previous[index] == line:
                continue
            parts.append(f"\033[{index + 1};1H")
            parts.append(line)
            parts.append("\033[K")

        for index in range(len(lines), len(previous)):
            parts.append(f"\033[{index + 1};1H\033[K")

        if parts:
            parts.append("\033[H")
            sys.stdout.write("".join(parts))
            sys.stdout.flush()
        self._previous = lines


def draw_frame(frame: str) -> None:
    """Repeint une image entière depuis la position d'origine."""
    sys.stdout.write("\033[H")
    sys.stdout.write(frame)
    sys.stdout.flush()


@contextlib.contextmanager
def terminal_session() -> Iterator[None]:
    """Prépare le terminal et restaure toujours son curseur et ses couleurs."""
    enable_windows_ansi()
    use_utf8_output()
    sys.stdout.write("\033[2J\033[H\033[?25l")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\033[0m\033[?25h\n")
        sys.stdout.flush()


def run_animation(
    render_frame: Callable[[int, int, int], str],
    *,
    fps: float,
    stopped_message: str,
    size: Callable[[], tuple[int, int]],
    on_frame: Callable[[str], None] | None = None,
) -> None:
    """Rend des images numérotées à une cadence cible stable, jusqu'à interruption.

    ``size`` est relu périodiquement pour qu'une fenêtre redimensionnée se
    recompose au lieu de se déchirer, et ``render_frame`` reçoit les dimensions
    courantes de la grille.
    """
    if fps <= 0:
        raise ValueError("Le nombre d'images par seconde doit être positif.")

    frame_duration = 1.0 / fps
    next_frame_at = time.perf_counter()
    frame_index = 0
    cols, rows = size()
    screen = Screen()

    try:
        with terminal_session():
            while True:
                if frame_index % _RESIZE_POLL_FRAMES == 0:
                    current = size()
                    if current != (cols, rows):
                        cols, rows = current
                        sys.stdout.write("\033[2J")
                        screen.invalidate()

                frame = render_frame(frame_index, cols, rows)
                screen.draw(frame)
                if on_frame is not None:
                    on_frame(frame)
                frame_index += 1
                next_frame_at += frame_duration
                remaining = next_frame_at - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                elif remaining < -frame_duration:
                    next_frame_at = time.perf_counter()
    except KeyboardInterrupt:
        print(stopped_message)
