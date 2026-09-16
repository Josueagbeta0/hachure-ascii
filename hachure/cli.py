"""Interface en ligne de commande publique de tous les moteurs de rendu."""

from __future__ import annotations

import argparse
import contextlib
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Sequence

from hachure import __version__
from hachure.charsets import (
    CHARSETS,
    DEFAULT_CHARSET,
    calibrate,
    find_monospace_font,
    get_charset,
)
from hachure.color import COLOR_DEPTHS, ColorDepth, detect_color_depth
from hachure.export import ExportError, FrameRecorder, strip_ansi
from hachure.media.image import (
    ImageRenderError,
    get_image_dimensions,
    render_image,
)
from hachure.media.video import (
    VideoOptions,
    VideoRenderError,
    list_camera_devices,
    play_camera,
    play_video,
)
from hachure.menu import executer_menu
from hachure.render import CELL_MODES, RenderStyle
from hachure.renderers import DEMOS, get_demo
from hachure.terminal import (
    FIT_MODES,
    default_char_aspect,
    enable_windows_ansi,
    fit_demo_size,
    fit_source_size,
    run_animation,
    source_crop,
    terminal_size,
    use_utf8_output,
)
from hachure.tone import ToneMapper


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("doit être strictement positif")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("doit être nul ou positif")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("doit être un nombre fini strictement positif")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("doit être un nombre fini nul ou positif")
    return parsed


def _unit_float(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("doit être compris entre 0 et 1")
    return parsed


def _char_aspect(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 2.0:
        raise argparse.ArgumentTypeError("doit être compris entre 0.1 et 2.0")
    return parsed


def _gamma(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 5.0:
        raise argparse.ArgumentTypeError("doit être compris entre 0.1 et 5.0")
    return parsed


def _audio_delay(value: str) -> float:
    parsed = float(value)
    if not -30 <= parsed <= 30:
        raise argparse.ArgumentTypeError("doit être compris entre -30 et 30 secondes")
    return parsed


def _add_style_options(parser: argparse.ArgumentParser, *, default_color: bool) -> None:
    parser.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default=DEFAULT_CHARSET,
        help="rampe luminosité-vers-caractère (défaut : %(default)s)",
    )
    parser.add_argument(
        "--invert", action="store_true", help="inverse les caractères sombres et clairs"
    )
    parser.add_argument(
        "--cells",
        choices=CELL_MODES,
        default="char",
        help="un pixel par cellule, ou deux pixels empilés par cellule (défaut : %(default)s)",
    )
    parser.add_argument(
        "--half",
        dest="cells",
        action="store_const",
        const="half",
        help="raccourci de --cells half ; double la résolution verticale",
    )
    parser.add_argument(
        "--color",
        dest="color",
        action="store_true",
        default=default_color,
        help="active la sortie en couleur",
    )
    parser.add_argument(
        "--no-color", dest="color", action="store_false", help="force une sortie monochrome"
    )
    parser.add_argument(
        "--mono", dest="color", action="store_false", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--color-depth",
        choices=("auto", *COLOR_DEPTHS),
        default="auto",
        help="court-circuite la détection de couleur du terminal (défaut : %(default)s)",
    )
    parser.add_argument(
        "--quant",
        type=_positive_int,
        default=4,
        help="pas de quantification des couleurs, pour réduire la sortie ANSI (défaut : %(default)s)",
    )
    parser.add_argument(
        "--edges",
        action="store_true",
        help="remplace le caractère de rampe par un glyphe de ligne là où un contour "
        "traverse la cellule, ce qui rend les formes lisibles",
    )
    parser.add_argument(
        "--edge-strength",
        type=_unit_float,
        default=0.5,
        help="force minimale d'un contour pour afficher un glyphe, de 0 à 1 "
        "(défaut : %(default)s)",
    )
    parser.add_argument(
        "--auto-levels",
        action="store_true",
        help="étire chaque image sur toute la rampe, au lieu de la seule plage "
        "que la source utilise",
    )
    parser.add_argument(
        "--gamma",
        type=_gamma,
        default=1.0,
        help="mise en forme des tons moyens ; au-dessus de 1 ça éclaircit (défaut : %(default)s)",
    )


def _add_geometry_options(parser: argparse.ArgumentParser, *, default_width: int) -> None:
    parser.add_argument(
        "--width",
        type=_positive_int,
        default=default_width,
        help="largeur maximale en caractères (défaut : %(default)s)",
    )
    parser.add_argument(
        "--height", type=_positive_int, help="hauteur maximale en caractères"
    )
    parser.add_argument(
        "--fit",
        choices=FIT_MODES,
        default="contain",
        help="encadre la source de bandes, ou la recadre pour remplir le terminal "
        "(défaut : %(default)s)",
    )
    parser.add_argument(
        "--char-aspect",
        type=_char_aspect,
        help="largeur d'une cellule divisée par sa hauteur, pour votre police (défaut : 0.5)",
    )


def _add_record_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--record",
        type=Path,
        metavar="PATH",
        help="écrit ce qui est rendu dans un fichier .mp4 ou .gif",
    )
    parser.add_argument(
        "--font", type=Path, help=".ttf à chasse fixe utilisé à l'enregistrement"
    )
    parser.add_argument(
        "--font-size",
        type=_positive_int,
        default=16,
        help="taille de police utilisée à l'enregistrement (défaut : %(default)s)",
    )


def _resolve_color_depth(args: argparse.Namespace) -> ColorDepth:
    if not args.color:
        return "none"
    if args.color_depth != "auto":
        depth: ColorDepth = args.color_depth
        return depth
    detected = detect_color_depth()
    # Un --color explicite doit produire de la couleur même redirigé vers un fichier.
    return detected if detected != "none" else "truecolor"


def _build_style(args: argparse.Namespace) -> RenderStyle:
    return RenderStyle(
        ramp=get_charset(args.charset, invert=args.invert),
        cell_mode=args.cells,
        color_depth=_resolve_color_depth(args),
        quantization=args.quant,
        edges=args.edges,
        edge_strength=args.edge_strength,
    )


def _build_tone(args: argparse.Namespace) -> ToneMapper | None:
    mapper = ToneMapper(gamma=args.gamma, auto_levels=args.auto_levels)
    return mapper if mapper.active else None


@contextlib.contextmanager
def _recorder(args: argparse.Namespace, fps: float) -> Iterator[FrameRecorder | None]:
    destination = getattr(args, "record", None)
    if destination is None:
        yield None
        return
    recorder = FrameRecorder(
        destination.expanduser().resolve(),
        fps=fps,
        font_size=args.font_size,
        font_path=args.font.expanduser().resolve() if args.font else None,
    )
    try:
        yield recorder
    finally:
        recorder.close()
        if recorder.frames:
            print(f"{recorder.frames} images enregistrées dans {recorder.destination}")


class _FrenchHelpFormatter(argparse.HelpFormatter):
    """Remplace le préfixe « usage: », qu'argparse ne rend pas configurable."""

    def add_usage(self, usage, actions, groups, prefix=None):
        # Tester None, pas la valeur de vérité : argparse appelle add_usage avec
        # un préfixe vide pour calculer le « prog » des sous-commandes.
        if prefix is None:
            prefix = "utilisation : "
        super().add_usage(usage, actions, groups, prefix)


def _localize(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Francise les libellés qu'argparse produit lui-même.

    argparse fait passer ses propres textes par gettext et CPython ne livre
    aucun catalogue français ; les titres de sections ne sont joignables que par
    ces attributs, privés mais stables depuis Python 3. Les parseurs sont créés
    avec ``add_help=False`` pour que ``-h`` soit déclaré ici, en premier, avec
    un texte traduit.
    """
    parser._positionals.title = "arguments positionnels"
    parser._optionals.title = "options"
    parser.add_argument(
        "-h", "--help", action="help", help="affiche ce message d'aide et quitte"
    )
    return parser


def _subparser(subparsers, name: str, *, help: str) -> argparse.ArgumentParser:
    return _localize(
        subparsers.add_parser(
            name, help=help, add_help=False, formatter_class=_FrenchHelpFormatter
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _localize(
        argparse.ArgumentParser(
            prog="hachure",
            description="Rend images, vidéos, caméras et art 3D procédural dans un terminal.",
            add_help=False,
            formatter_class=_FrenchHelpFormatter,
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="affiche la version du programme et quitte",
    )
    # Non obligatoire : « hachure » tout court ouvre le menu interactif.
    subparsers = parser.add_subparsers(dest="command")

    menu_parser = _subparser(
        subparsers, "menu", help="ouvre le menu interactif (comportement par défaut)"
    )
    menu_parser.set_defaults(handler=_run_menu)

    list_parser = _subparser(subparsers, "list", help="liste les moteurs de rendu disponibles")
    list_parser.set_defaults(handler=_run_list)

    doctor_parser = _subparser(
        subparsers, "doctor", help="vérifie les dépendances et les capacités du terminal"
    )
    doctor_parser.set_defaults(handler=_run_doctor)

    calibrate_parser = _subparser(
        subparsers, "calibrate", help="construit une rampe de caractères mesurée sur une police"
    )
    calibrate_parser.add_argument(
        "--font", type=Path, help=".ttf à chasse fixe à mesurer"
    )
    calibrate_parser.add_argument(
        "--length",
        type=_positive_int,
        default=12,
        help="nombre de caractères que la rampe doit contenir (défaut : %(default)s)",
    )
    calibrate_parser.add_argument(
        "--size",
        type=_positive_int,
        default=32,
        help="taille en pixels à laquelle les glyphes sont mesurés (défaut : %(default)s)",
    )
    calibrate_parser.set_defaults(handler=_run_calibrate)

    image_parser = _subparser(subparsers, "image", help="convertit une image fixe en ASCII")
    image_parser.add_argument("path", type=Path, help="chemin vers une image")
    _add_geometry_options(image_parser, default_width=100)
    _add_style_options(image_parser, default_color=False)
    image_parser.add_argument(
        "-o", "--output", type=Path, help="écrit le texte dans un fichier UTF-8"
    )
    image_parser.set_defaults(handler=_run_image)

    video_parser = _subparser(subparsers, "video", help="lit une vidéo en ASCII")
    video_parser.add_argument("path", type=Path, help="chemin vers une vidéo")
    _add_geometry_options(video_parser, default_width=160)
    _add_style_options(video_parser, default_color=False)
    _add_playback_options(video_parser)
    _add_record_options(video_parser)
    video_parser.add_argument(
        "--loop", action="store_true", help="redémarre quand la vidéo se termine"
    )
    video_parser.add_argument(
        "--start",
        type=_nonnegative_float,
        default=0.0,
        help="position de départ en secondes (défaut : %(default)s)",
    )
    video_parser.add_argument(
        "--duration", type=_positive_float, help="arrête après ce nombre de secondes"
    )
    video_parser.add_argument(
        "--no-audio", action="store_true", help="désactive l'audio via FFplay"
    )
    video_parser.add_argument(
        "--audio-delay",
        type=_audio_delay,
        default=0.0,
        help="décalage audio en secondes ; une valeur positive retarde l'audio",
    )
    video_parser.set_defaults(handler=_run_video)

    camera_parser = _subparser(subparsers, "camera", help="lit une caméra en direct en ASCII")
    camera_parser.add_argument("--device", help="nom ou chemin de la caméra")
    camera_parser.add_argument(
        "--list", action="store_true", help="liste les caméras disponibles et quitte"
    )
    camera_parser.add_argument(
        "--size", help="taille de capture demandée, par exemple 1280x720"
    )
    camera_parser.add_argument(
        "--duration", type=_positive_float, help="arrête après ce nombre de secondes"
    )
    _add_geometry_options(camera_parser, default_width=160)
    _add_style_options(camera_parser, default_color=True)
    _add_playback_options(camera_parser, default_fps=15.0)
    _add_record_options(camera_parser)
    camera_parser.set_defaults(handler=_run_camera)

    demo_parser = _subparser(subparsers, "demo", help="lance un moteur de rendu procédural")
    demo_parser.add_argument("name", choices=sorted(DEMOS), help="nom de la démo")
    demo_parser.add_argument("--width", type=_positive_int, help="largeur en caractères")
    demo_parser.add_argument("--height", type=_positive_int, help="hauteur en caractères")
    demo_parser.add_argument(
        "--fps",
        type=_positive_float,
        default=30.0,
        help="cadence de lecture visée (défaut : %(default)s)",
    )
    demo_parser.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default=DEFAULT_CHARSET,
        help="rampe luminosité-vers-caractère (défaut : %(default)s)",
    )
    demo_parser.add_argument(
        "--invert", action="store_true", help="inverse les caractères sombres et clairs"
    )
    _add_record_options(demo_parser)
    demo_parser.set_defaults(handler=_run_demo)

    return parser


def _add_playback_options(
    parser: argparse.ArgumentParser, *, default_fps: float = 20.0
) -> None:
    parser.add_argument(
        "--fps",
        type=_positive_float,
        default=default_fps,
        help="cadence de lecture visée (défaut : %(default)s)",
    )
    parser.add_argument(
        "--smoothing",
        type=_unit_float,
        default=1.0,
        help="lissage temporel : 1 est net, les valeurs plus basses ajoutent des traînées",
    )
    parser.add_argument(
        "--max-frame-skip",
        type=_nonnegative_int,
        default=5,
        help="nombre maximal d'images consécutives abandonnées pour rattraper le retard (défaut : %(default)s)",
    )


def _run_list(_args: argparse.Namespace) -> int:
    print("Moteurs de rendu d'entrée :")
    print("  image      Images fixes, via Pillow")
    print("  video      Fichiers vidéo, via FFmpeg")
    print("  camera     Capture caméra en direct, via FFmpeg")
    print("\nDémos procédurales :")
    for demo in DEMOS.values():
        print(f"  {demo.name:<10} {demo.description}")
    return 0


def _tool_version(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        return "absent du PATH"
    try:
        result = subprocess.run(
            [name, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
        first = result.stdout.splitlines()[0] if result.stdout else ""
        return first or path
    except (OSError, subprocess.SubprocessError, IndexError):
        return path


def _run_doctor(_args: argparse.Namespace) -> int:
    columns, rows = terminal_size()
    print(f"{'hachure':<13} {__version__}")
    print(f"python        {sys.version.split()[0]} ({sys.executable})")

    for module in ("numpy", "PIL"):
        try:
            imported = __import__(module)
            version = getattr(imported, "__version__", "inconnue")
            print(f"{module:<13} {version}")
        except ImportError:
            print(f"{module:<13} ABSENT")

    for tool in ("ffmpeg", "ffplay", "ffprobe"):
        print(f"{tool:<13} {_tool_version(tool)}")

    print(f"terminal      {columns} x {rows} cellules")
    print(f"profondeur    {detect_color_depth()}")
    print(f"rapport cell. {default_char_aspect()}")
    print(f"tty stdout    {sys.stdout.isatty()}")
    print(f"codec stdout  {getattr(sys.stdout, 'encoding', 'inconnu')}")

    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print(
            "\nLa lecture vidéo a besoin de "
            + ", ".join(missing)
            + ". Installez FFmpeg puis rouvrez votre terminal."
        )
        return 1
    return 0


def _run_calibrate(args: argparse.Namespace) -> int:
    font = args.font.expanduser().resolve() if args.font else find_monospace_font()
    if font is None:
        raise ValueError(
            "Aucune police à chasse fixe n'a été trouvée. Passez --font avec un chemin vers un .ttf."
        )
    if not font.is_file():
        raise ValueError(f"Police introuvable : {font}")

    ramp = calibrate(font, size=args.size, length=args.length)
    print(f"Police : {font}")
    print(f"Rampe  : {ramp!r}")
    print(
        "\nAjoutez-la à CHARSETS dans charsets.py pour l'utiliser avec --charset, "
        "ou comparez-la aux rampes intégrées :"
    )
    for name, existing in sorted(CHARSETS.items()):
        print(f"  {name:<10} {existing!r}")
    return 0


def _run_image(args: argparse.Namespace) -> int:
    path = args.path.expanduser().resolve()
    if not path.is_file():
        raise ImageRenderError(f"Image introuvable : {path}")
    style = _build_style(args)
    source_width, source_height = get_image_dimensions(path)
    width, height = fit_source_size(
        source_width,
        source_height,
        max_width=args.width,
        max_height=args.height,
        char_aspect=args.char_aspect,
        fit=args.fit,
    )
    crop = None
    if args.fit == "cover":
        crop = source_crop(
            source_width,
            source_height,
            width,
            height,
            char_aspect=args.char_aspect,
        )
    output = render_image(
        path,
        width=width,
        height=height,
        style=style,
        crop=crop,
        tone=_build_tone(args),
    )
    if args.output:
        destination = args.output.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output + "\n", encoding="utf-8")
        plain = strip_ansi(output)
        columns = max((len(line) for line in plain.split("\n")), default=0)
        print(f"Image ASCII {columns} x {height} écrite dans {destination}")
    else:
        print(output)
    return 0


def _video_options(args: argparse.Namespace, **overrides: object) -> VideoOptions:
    options = VideoOptions(
        fps=args.fps,
        max_width=args.width,
        max_height=args.height,
        fit=args.fit,
        char_aspect=args.char_aspect,
        smoothing=args.smoothing,
        max_frame_skip=args.max_frame_skip,
        audio=not getattr(args, "no_audio", True),
        audio_delay=getattr(args, "audio_delay", 0.0),
        loop=getattr(args, "loop", False),
        start=getattr(args, "start", 0.0),
        duration=getattr(args, "duration", None),
    )
    if overrides:
        from dataclasses import replace

        options = replace(options, **overrides)  # type: ignore[arg-type]
    return options


def _run_video(args: argparse.Namespace) -> int:
    style = _build_style(args)
    options = _video_options(args)
    with _recorder(args, args.fps) as recorder:
        play_video(
            args.path.expanduser().resolve(),
            options=options,
            style=style,
            sink=recorder,
            tone=_build_tone(args),
        )
    return 0


def _run_camera(args: argparse.Namespace) -> int:
    if args.list:
        devices = list_camera_devices()
        if not devices:
            print("Aucune caméra signalée. Sous Linux et macOS, passez --device.")
            return 1
        print("Caméras :")
        for device in devices:
            print(f"  {device}")
        return 0

    style = _build_style(args)
    options = _video_options(args, audio=False)
    with _recorder(args, args.fps) as recorder:
        play_camera(
            device=args.device,
            size=args.size,
            options=options,
            style=style,
            sink=recorder,
            tone=_build_tone(args),
        )
    return 0


def _run_demo(args: argparse.Namespace) -> int:
    demo = get_demo(args.name)
    ramp = get_charset(args.charset, invert=args.invert)

    def current_size() -> tuple[int, int]:
        return fit_demo_size(
            default_width=demo.default_width,
            height_ratio=demo.height_ratio,
            width=args.width,
            height=args.height,
        )

    with _recorder(args, args.fps) as recorder:
        run_animation(
            lambda index, cols, rows: demo.render(index, cols, rows, ramp),
            fps=args.fps,
            stopped_message=f"{demo.name.capitalize()} arrêté.",
            size=current_size,
            on_frame=recorder.capture if recorder is not None else None,
        )
    return 0


def _run_menu(_args: argparse.Namespace) -> int:
    # Le menu dessine des séquences ANSI et des accents : il a besoin du mode VT
    # de Windows et d'une sortie UTF-8, que terminal_session() n'ouvre qu'autour
    # d'une animation.
    enable_windows_ansi()
    use_utf8_output()
    return executer_menu(main)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return _run_menu(args)
    try:
        return int(args.handler(args))
    except (
        ImageRenderError,
        VideoRenderError,
        ExportError,
        ValueError,
        OSError,
    ) as exc:
        parser.exit(2, f"erreur : {exc}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
