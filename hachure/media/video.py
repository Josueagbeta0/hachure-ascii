"""Lecture vidéo et caméra dans le terminal, adossée à FFmpeg."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from hachure.i18n import T
from hachure.render import RenderStyle, render_array
from hachure.terminal import (
    FitMode,
    Screen,
    fit_source_size,
    source_crop,
    terminal_session,
    terminal_size,
)
from hachure.tone import ToneMapper

# Le terminal est mesuré à cette fréquence, en images, pour repérer un redimensionnement de la fenêtre.
_RESIZE_POLL_FRAMES = 15


class VideoRenderError(RuntimeError):
    pass


class FrameSink(Protocol):
    """Tout ce qui veut une copie de chaque image rendue, un enregistreur par exemple."""

    def capture(self, frame: str) -> None: ...


@dataclass(frozen=True)
class VideoOptions:
    """Comportement de lecture et de dimensionnement, indépendant du style pixel-vers-texte."""

    fps: float = 20.0
    max_width: int = 160
    max_height: int | None = None
    fit: FitMode = "contain"
    char_aspect: float | None = None
    smoothing: float = 1.0
    max_frame_skip: int = 5
    audio: bool = True
    audio_delay: float = 0.0
    loop: bool = False
    start: float = 0.0
    duration: float | None = None


@dataclass(frozen=True)
class MediaSource:
    """Une entrée FFmpeg, accompagnée de ce que le moteur de rendu doit en savoir."""

    input_args: list[str]
    label: str
    dimensions: tuple[int, int] | None = None
    seekable: bool = True
    audio_args: list[str] = field(default_factory=list)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_args)


def _load_numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise VideoRenderError(T("erreur.video_numpy")) from exc
    return numpy


def read_frame(stream: BinaryIO, size: int) -> bytes | None:
    """Lit une image brute complète ; renvoie None en fin de flux ou sur une image partielle."""
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def _probe(video: Path) -> dict[str, Any] | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                "-of",
                "json",
                str(video),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        payload = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    streams = payload.get("streams") or []
    return streams[0] if streams else None


def _stream_rotation(stream: dict[str, Any]) -> int:
    """Lit la rotation d'affichage que FFmpeg appliquera avant même qu'on voie une image."""
    candidates: list[Any] = []
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        candidates.append(tags["rotate"])
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            candidates.append(side_data["rotation"])
    for candidate in candidates:
        try:
            return int(round(float(candidate))) % 360
        except (TypeError, ValueError):
            continue
    return 0


def get_video_dimensions(video: Path) -> tuple[int, int] | None:
    """Renvoie la taille d'image affichée, en tenant compte des métadonnées de rotation.

    FFmpeg pivote automatiquement au décodage : un plan de téléphone en portrait
    stocké en 1920x1080 arrive donc au moteur de rendu en 1080x1920, et doit être
    mesuré ainsi.
    """
    stream = _probe(video)
    if stream is None:
        return None
    try:
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    if _stream_rotation(stream) in (90, 270):
        width, height = height, width
    return width, height


def file_source(video: Path) -> MediaSource:
    if not video.is_file():
        raise VideoRenderError(T("erreur.video_introuvable", chemin=video))
    return MediaSource(
        input_args=["-i", str(video)],
        label=video.name,
        dimensions=get_video_dimensions(video),
        seekable=True,
        audio_args=["-i", str(video)],
    )


def list_camera_devices() -> list[str]:
    """Renvoie les noms de caméras que FFmpeg sait ouvrir sur cette plateforme."""
    if shutil.which("ffmpeg") is None:
        raise VideoRenderError(T("erreur.ffmpeg_absent"))
    system = platform.system()
    if system != "Windows":
        return []

    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    return parse_dshow_devices(result.stderr)


def parse_dshow_devices(output: str) -> list[str]:
    """Extrait les noms de caméras de la liste de périphériques de FFmpeg.

    Les anciennes versions regroupent les périphériques sous des en-têtes
    « DirectShow video devices », tandis que FFmpeg 8 et suivants marquent plutôt
    chaque ligne d'un ``(video)``, ``(audio)`` ou ``(none)``. Les deux
    dispositions sont lues ici.
    """
    tagged: list[str] = []
    sectioned: list[str] = []
    video_section: bool | None = None

    for line in output.splitlines():
        if "Alternative name" in line:
            continue
        if "DirectShow video devices" in line:
            video_section = True
            continue
        if "DirectShow audio devices" in line:
            video_section = False
            continue

        marked = re.search(r'"([^"]+)"\s*\((video|audio|none)\)', line)
        if marked is not None:
            if marked.group(2) != "audio":
                tagged.append(marked.group(1))
            continue

        if video_section:
            quoted = re.search(r'"([^"]+)"', line)
            if quoted is not None:
                sectioned.append(quoted.group(1))

    return tagged or sectioned


def camera_source(device: str | None = None, *, size: str | None = None) -> MediaSource:
    """Construit une entrée caméra en direct pour la plateforme courante."""
    system = platform.system()
    arguments: list[str] = []

    if system == "Windows":
        name = device
        if name is None:
            devices = list_camera_devices()
            if not devices:
                raise VideoRenderError(T("erreur.camera_absente"))
            name = devices[0]
        arguments = ["-f", "dshow"]
        if size:
            arguments += ["-video_size", size]
        arguments += ["-i", f"video={name}"]
        label = name
    elif system == "Darwin":
        name = device or "0"
        arguments = ["-f", "avfoundation"]
        if size:
            arguments += ["-video_size", size]
        arguments += ["-i", name]
        label = f"avfoundation:{name}"
    else:
        name = device or "/dev/video0"
        arguments = ["-f", "v4l2"]
        if size:
            arguments += ["-video_size", size]
        arguments += ["-i", name]
        label = name

    return MediaSource(
        input_args=arguments,
        label=label,
        dimensions=None,
        seekable=False,
    )


def _smooth(current: Any, previous: Any | None, factor: float) -> Any:
    if previous is None or factor >= 0.999:
        return current
    return previous + (current - previous) * factor


def _frame_array(raw: bytes, rows: int, cols: int, color: bool, np: Any) -> Any:
    shape = (rows, cols, 3) if color else (rows, cols)
    return np.frombuffer(raw, dtype=np.uint8).reshape(shape).astype(np.float32)


def _start_audio(source: MediaSource, offset: float) -> subprocess.Popen[bytes] | None:
    if not source.has_audio:
        return None
    command = ["ffplay", "-nodisp", "-vn", "-autoexit", "-loglevel", "quiet"]
    if offset > 0:
        command += ["-ss", f"{offset:.3f}"]
    command += source.audio_args[1:] if source.audio_args[0] == "-i" else source.audio_args
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


def _grid_for(
    source: MediaSource, options: VideoOptions, style: RenderStyle
) -> tuple[int, int, tuple[int, int, int, int] | None]:
    """Choisit la grille de caractères et, en ajustement « cover », le recadrage de la source."""
    source_width, source_height = source.dimensions or (16, 9)
    cols, rows = fit_source_size(
        source_width,
        source_height,
        max_width=options.max_width,
        max_height=options.max_height,
        char_aspect=options.char_aspect,
        fit=options.fit,
    )
    crop = None
    if options.fit == "cover" and source.dimensions is not None:
        crop = source_crop(
            source_width,
            source_height,
            cols,
            rows,
            char_aspect=options.char_aspect,
        )
    return cols, rows, crop


def _build_command(
    source: MediaSource,
    options: VideoOptions,
    style: RenderStyle,
    *,
    cols: int,
    rows: int,
    crop: tuple[int, int, int, int] | None,
    position: float,
) -> list[str]:
    pixel_cols = style.pixel_cols(cols)
    pixel_rows = style.pixel_rows(rows)
    filters = [f"fps={options.fps}"]
    if crop is not None:
        crop_width, crop_height, offset_x, offset_y = crop
        filters.append(f"crop={crop_width}:{crop_height}:{offset_x}:{offset_y}")
        filters.append(f"scale={pixel_cols}:{pixel_rows}")
    elif options.fit == "cover":
        # Les dimensions de la source sont inconnues (caméra en direct) : on
        # laisse FFmpeg dépasser la cible puis on rogne l'excédent.
        filters.append(
            f"scale={pixel_cols}:{pixel_rows}:force_original_aspect_ratio=increase"
        )
        filters.append(f"crop={pixel_cols}:{pixel_rows}")
    else:
        filters.append(f"scale={pixel_cols}:{pixel_rows}")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if source.seekable and position > 0:
        command += ["-ss", f"{position:.3f}"]
    command += source.input_args
    if options.duration is not None:
        remaining = options.duration - max(0.0, position - options.start)
        if remaining <= 0:
            remaining = options.duration
        command += ["-t", f"{remaining:.3f}"]
    command += [
        "-vf",
        ",".join(filters),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24" if style.colored else "gray",
        "-",
    ]
    return command


def _describe(
    source: MediaSource,
    options: VideoOptions,
    style: RenderStyle,
    cols: int,
    rows: int,
) -> None:
    pixels = f"{style.pixel_cols(cols)} x {style.pixel_rows(rows)} {T('lecture.pixels')}"
    grille = f"{cols} x {rows} {T('doctor.cellules')}"
    audio = T("lecture.active") if options.audio and source.has_audio else T("lecture.desactive")
    # Les libellés sont alignés sur le plus long, qui diffère selon la langue.
    largeur = max(len(T(c)) for c in
                  ("lecture.source", "lecture.rendu", "lecture.cellules", "lecture.audio"))
    print(f"{T('lecture.source').ljust(largeur)} : {source.label}")
    print(f"{T('lecture.rendu').ljust(largeur)} : {grille} ({pixels}) — {options.fps:g} {T('lecture.ips')}")
    print(
        f"{T('lecture.cellules').ljust(largeur)} : {style.cell_mode}"
        f"    {T('lecture.couleur')} : {style.color_depth}"
        f"    {T('lecture.ajustement')} : {options.fit}"
    )
    print(f"{T('lecture.audio').ljust(largeur)} : {audio}")
    print(T("lecture.demarrage"))


def play_source(
    source: MediaSource,
    *,
    options: VideoOptions,
    style: RenderStyle,
    sink: FrameSink | None = None,
    tone: ToneMapper | None = None,
) -> None:
    """Décode une source média et l'affiche dans le terminal jusqu'à sa fin."""
    if shutil.which("ffmpeg") is None:
        raise VideoRenderError(T("erreur.ffmpeg_absent"))
    audio_wanted = options.audio and source.has_audio
    if audio_wanted and shutil.which("ffplay") is None:
        raise VideoRenderError(T("erreur.ffplay_absent"))

    np = _load_numpy()
    palette = style.palette()
    cols, rows, crop = _grid_for(source, options, style)
    _describe(source, options, style, cols, rows)

    frame_duration = 1.0 / options.fps
    screen = Screen()
    interrupted = False

    audio_process: subprocess.Popen[bytes] | None = None
    video_process: subprocess.Popen[bytes] | None = None

    try:
        with terminal_session():
            position = options.start
            wall_start = time.perf_counter()
            frames_shown = 0
            previous_array = None
            last_size = terminal_size()

            if audio_wanted and options.audio_delay <= 0:
                audio_process = _start_audio(source, options.start)
                if options.audio_delay < 0:
                    time.sleep(-options.audio_delay)
            audio_due_at = (
                wall_start + options.audio_delay
                if audio_wanted and options.audio_delay > 0
                else None
            )

            while True:
                channels = 3 if style.colored else 1
                pixel_cols = style.pixel_cols(cols)
                pixel_rows = style.pixel_rows(rows)
                frame_size = pixel_cols * pixel_rows * channels
                command = _build_command(
                    source,
                    options,
                    style,
                    cols=cols,
                    rows=rows,
                    crop=crop,
                    position=position,
                )
                video_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=10**8,
                )
                if video_process.stdout is None:
                    raise VideoRenderError(T("erreur.flux_absent"))

                segment_start = time.perf_counter()
                segment_frames = 0
                consecutive_drops = 0
                restart_for_resize = False

                while True:
                    raw = read_frame(video_process.stdout, frame_size)
                    if raw is None:
                        break

                    now = time.perf_counter()
                    if audio_due_at is not None and now >= audio_due_at:
                        audio_process = _start_audio(source, options.start)
                        audio_due_at = None

                    if frames_shown % _RESIZE_POLL_FRAMES == 0:
                        current_size = terminal_size()
                        if current_size != last_size:
                            last_size = current_size
                            restart_for_resize = True
                            break

                    target = segment_start + segment_frames * frame_duration
                    segment_frames += 1
                    lag = now - target
                    if lag > frame_duration and consecutive_drops < options.max_frame_skip:
                        consecutive_drops += 1
                        frames_shown += 1
                        continue

                    consecutive_drops = 0
                    if lag < 0:
                        time.sleep(-lag)

                    array = _frame_array(
                        raw, pixel_rows, pixel_cols, style.colored, np
                    )
                    array = _smooth(array, previous_array, options.smoothing)
                    previous_array = array
                    frame = render_array(
                        array, style, np, palette=palette, tone=tone
                    )
                    screen.draw(frame)
                    if sink is not None:
                        sink.capture(frame)
                    frames_shown += 1

                elapsed = segment_frames * frame_duration
                _stop_process(video_process)

                if restart_for_resize:
                    position += elapsed
                    cols, rows, crop = _grid_for(source, options, style)
                    previous_array = None
                    screen.invalidate()
                    sys.stdout.write("\033[2J")
                    continue

                if video_process.returncode not in (0, None) and segment_frames == 0:
                    decoder_error = ""
                    if video_process.stderr is not None:
                        decoder_error = (
                            video_process.stderr.read().decode(errors="replace").strip()
                        )
                    raise VideoRenderError(
                        decoder_error or T("erreur.decodage")
                    )

                if not options.loop:
                    break

                position = options.start
                previous_array = None
                if tone is not None:
                    tone.reset()
                _stop_process(audio_process)
                audio_process = (
                    _start_audio(source, options.start) if audio_wanted else None
                )
                screen.invalidate()
                sys.stdout.write("\033[2J")

    except KeyboardInterrupt:
        interrupted = True
    except OSError as exc:
        raise VideoRenderError(T("erreur.lecture_demarrage", cause=exc)) from exc
    except subprocess.SubprocessError as exc:
        raise VideoRenderError(T("erreur.processus_media", cause=exc)) from exc
    finally:
        _stop_process(video_process)
        _stop_process(audio_process)

    print(T("lecture.interrompue") if interrupted else T("lecture.terminee"))


def play_video(
    video: Path,
    *,
    options: VideoOptions,
    style: RenderStyle,
    sink: FrameSink | None = None,
    tone: ToneMapper | None = None,
) -> None:
    """Lit un fichier vidéo. Conservé comme point d'entrée pratique pour les entrées fichier."""
    if shutil.which("ffmpeg") is None:
        raise VideoRenderError(T("erreur.ffmpeg_absent"))
    source = file_source(video)
    if options.duration is not None and options.duration <= 0:
        raise VideoRenderError(T("erreur.duree_positive"))
    play_source(source, options=options, style=style, sink=sink, tone=tone)


def play_camera(
    *,
    device: str | None,
    size: str | None,
    options: VideoOptions,
    style: RenderStyle,
    sink: FrameSink | None = None,
    tone: ToneMapper | None = None,
) -> None:
    source = camera_source(device, size=size)
    try:
        play_source(
            source,
            options=replace(options, audio=False, loop=False, start=0.0),
            style=style,
            sink=sink,
            tone=tone,
        )
    except VideoRenderError as exc:
        # Ces deux sous-chaînes proviennent de la sortie de FFmpeg : ne pas les traduire.
        if "I/O error" in str(exc) or "Could not find video device" in str(exc):
            raise VideoRenderError(f"{exc}\n{T('erreur.camera_acces')}") from exc
        raise
