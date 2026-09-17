"""Enregistre les images rendues dans le terminal vers une vidéo ou un GIF animé.

Les images arrivent sous la forme du même texte à codes d'échappement que celui
envoyé au terminal : l'enregistreur relit donc ces séquences et les peint avec
une police à chasse fixe. Ce qui est écrit est ce que le terminal a montré,
couleurs comprises.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from hachure.i18n import T

RGB = tuple[int, int, int]

DEFAULT_FOREGROUND: RGB = (200, 200, 200)
DEFAULT_BACKGROUND: RGB = (12, 12, 14)

_ANSI_PATTERN = re.compile(r"\033\[([0-9;]*)m")

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/lucon.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Menlo.ttc",
)

# Les niveaux du cube xterm-256, nécessaires pour défaire les codes 256 couleurs à l'enregistrement.
_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


class ExportError(RuntimeError):
    pass


def strip_ansi(text: str) -> str:
    return _ANSI_PATTERN.sub("", text)


def ansi256_to_rgb(index: int) -> RGB:
    if index < 16:
        base = 128 if index < 8 else 255
        return (
            base if index & 1 else 0,
            base if index & 2 else 0,
            base if index & 4 else 0,
        )
    if index < 232:
        offset = index - 16
        return (
            _CUBE_LEVELS[offset // 36],
            _CUBE_LEVELS[(offset // 6) % 6],
            _CUBE_LEVELS[offset % 6],
        )
    level = 8 + (index - 232) * 10
    return (level, level, level)


@dataclass
class _PenState:
    foreground: RGB = DEFAULT_FOREGROUND
    background: RGB | None = None


def _apply_sgr(parameters: str, pen: _PenState) -> None:
    codes = [int(value) if value else 0 for value in parameters.split(";")]
    index = 0
    while index < len(codes):
        code = codes[index]
        if code == 0:
            pen.foreground = DEFAULT_FOREGROUND
            pen.background = None
        elif code in (38, 48) and index + 1 < len(codes):
            selector = codes[index + 1]
            if selector == 2 and index + 4 < len(codes):
                color = (codes[index + 2], codes[index + 3], codes[index + 4])
                index += 4
            elif selector == 5 and index + 2 < len(codes):
                color = ansi256_to_rgb(codes[index + 2])
                index += 2
            else:
                index += 1
                continue
            if code == 38:
                pen.foreground = color
            else:
                pen.background = color
        elif code == 39:
            pen.foreground = DEFAULT_FOREGROUND
        elif code == 49:
            pen.background = None
        index += 1


def iter_runs(line: str) -> Iterator[tuple[int, str, RGB, RGB | None]]:
    """Produit les plages ``(colonne, texte, premier plan, arrière-plan)`` d'une ligne."""
    pen = _PenState()
    column = 0
    position = 0
    for match in _ANSI_PATTERN.finditer(line):
        text = line[position : match.start()]
        if text:
            yield column, text, pen.foreground, pen.background
            column += len(text)
        _apply_sgr(match.group(1), pen)
        position = match.end()
    tail = line[position:]
    if tail:
        yield column, tail, pen.foreground, pen.background


def _load_font(size: int) -> Any:
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise ExportError(T("erreur.enreg_pillow")) from exc

    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    raise ExportError(T("erreur.enreg_police"))


class FrameRecorder:
    """Peint les images avec une police à chasse fixe et les redirige vers FFmpeg."""

    def __init__(
        self,
        destination: Path,
        *,
        fps: float,
        font_size: int = 16,
        font_path: Path | None = None,
        background: RGB = DEFAULT_BACKGROUND,
    ) -> None:
        if shutil.which("ffmpeg") is None:
            raise ExportError(T("erreur.enreg_ffmpeg"))
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise ExportError(T("erreur.enreg_pillow")) from exc

        self._image_module = Image
        self._draw_module = ImageDraw
        self._destination = destination
        self._fps = fps
        self._background = background
        self._frames = 0
        self._process: subprocess.Popen[bytes] | None = None
        self._size: tuple[int, int] | None = None
        self._closed = False

        if font_path is not None:
            if not font_path.is_file():
                raise ExportError(T("erreur.police_introuvable", chemin=font_path))
            try:
                self._font = ImageFont.truetype(str(font_path), font_size)
            except OSError as exc:
                raise ExportError(T("erreur.police_chargement", chemin=font_path, cause=exc)) from exc
        else:
            self._font = _load_font(font_size)

        ascent, descent = self._font.getmetrics()
        self._cell_height = max(1, ascent + descent)
        self._cell_width = max(1, round(self._font.getlength("M")))
        self._ascent = ascent

    @property
    def frames(self) -> int:
        return self._frames

    @property
    def destination(self) -> Path:
        return self._destination

    def _render(self, frame: str) -> Any:
        lines = frame.split("\n")
        columns = max((len(strip_ansi(line)) for line in lines), default=1)
        width = max(2, columns * self._cell_width)
        height = max(2, len(lines) * self._cell_height)
        # yuv420p exige des dimensions paires.
        width += width % 2
        height += height % 2

        image = self._image_module.new("RGB", (width, height), self._background)
        draw = self._draw_module.Draw(image)

        for row, line in enumerate(lines):
            top = row * self._cell_height
            for column, text, foreground, background in iter_runs(line):
                left = column * self._cell_width
                if background is not None:
                    draw.rectangle(
                        (
                            left,
                            top,
                            left + len(text) * self._cell_width - 1,
                            top + self._cell_height - 1,
                        ),
                        fill=background,
                    )
                draw.text((left, top), text, font=self._font, fill=foreground)
        return image

    def _start(self, size: tuple[int, int]) -> None:
        width, height = size
        suffix = self._destination.suffix.lower()
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            f"{self._fps:g}",
            "-i",
            "-",
        ]
        if suffix == ".gif":
            command += [
                "-filter_complex",
                "[0:v]split[a][b];[a]palettegen=stats_mode=diff[p];"
                "[b][p]paletteuse=dither=bayer:bayer_scale=3",
            ]
        else:
            command += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        command.append(str(self._destination))

        self._destination.parent.mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._size = size

    def capture(self, frame: str) -> None:
        if self._closed:
            return
        image = self._render(frame)
        if self._process is None:
            self._start(image.size)
        elif image.size != self._size:
            # Un redimensionnement en cours d'enregistrement corromprait le flux
            # brut ; on complète ou on recadre à la taille avec laquelle FFmpeg a
            # été lancé.
            canvas = self._image_module.new("RGB", self._size, self._background)
            canvas.paste(image, (0, 0))
            image = canvas
        assert self._process is not None and self._process.stdin is not None
        try:
            self._process.stdin.write(image.tobytes())
        except (BrokenPipeError, OSError) as exc:
            self._closed = True
            raise ExportError(T("erreur.enreg_interrompu", cause=exc)) from exc
        self._frames += 1

    def close(self) -> None:
        if self._closed or self._process is None:
            self._closed = True
            return
        self._closed = True
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
            self._process.wait(timeout=60)
        except (OSError, subprocess.SubprocessError):
            try:
                self._process.kill()
            except OSError:
                pass
            return
        if self._process.returncode:
            details = ""
            if self._process.stderr is not None:
                details = self._process.stderr.read().decode(errors="replace").strip()
            raise ExportError(details or T("erreur.enreg_ecriture"))

    def __enter__(self) -> "FrameRecorder":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()
