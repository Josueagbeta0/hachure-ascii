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
from hachure.i18n import LANGUES, T, definir_langue, langue, normaliser
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
        raise argparse.ArgumentTypeError(T("validation.positif"))
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(T("validation.nul_ou_positif"))
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(T("validation.fini_positif"))
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(T("validation.fini_nul_ou_positif"))
    return parsed


def _unit_float(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError(T("validation.entre_0_et_1"))
    return parsed


def _char_aspect(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 2.0:
        raise argparse.ArgumentTypeError(T("validation.entre_01_et_2"))
    return parsed


def _gamma(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 5.0:
        raise argparse.ArgumentTypeError(T("validation.entre_01_et_5"))
    return parsed


def _audio_delay(value: str) -> float:
    parsed = float(value)
    if not -30 <= parsed <= 30:
        raise argparse.ArgumentTypeError(T("validation.decalage_audio"))
    return parsed


def _langue(value: str) -> str:
    """Accepte « fr », « en » ou « auto »."""
    choisi = value.strip().lower()
    if choisi == "auto" or normaliser(choisi):
        return choisi
    raise argparse.ArgumentTypeError(T("validation.langue"))


def _add_style_options(parser: argparse.ArgumentParser, *, default_color: bool) -> None:
    parser.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default=DEFAULT_CHARSET,
        help=T("aide.charset"),
    )
    parser.add_argument(
        "--invert", action="store_true", help=T("aide.invert")
    )
    parser.add_argument(
        "--cells",
        choices=CELL_MODES,
        default="char",
        help=T("aide.cells"),
    )
    parser.add_argument(
        "--half",
        dest="cells",
        action="store_const",
        const="half",
        help=T("aide.half"),
    )
    parser.add_argument(
        "--color",
        dest="color",
        action="store_true",
        default=default_color,
        help=T("aide.color"),
    )
    parser.add_argument(
        "--no-color", dest="color", action="store_false", help=T("aide.no_color")
    )
    parser.add_argument(
        "--mono", dest="color", action="store_false", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--color-depth",
        choices=("auto", *COLOR_DEPTHS),
        default="auto",
        help=T("aide.color_depth"),
    )
    parser.add_argument(
        "--quant",
        type=_positive_int,
        default=4,
        help=T("aide.quant"),
    )
    parser.add_argument(
        "--edges",
        action="store_true",
        help=T("aide.edges"),
    )
    parser.add_argument(
        "--edge-strength",
        type=_unit_float,
        default=0.5,
        help=T("aide.edge_strength"),
    )
    parser.add_argument(
        "--auto-levels",
        action="store_true",
        help=T("aide.auto_levels"),
    )
    parser.add_argument(
        "--gamma",
        type=_gamma,
        default=1.0,
        help=T("aide.gamma"),
    )


def _add_geometry_options(parser: argparse.ArgumentParser, *, default_width: int) -> None:
    parser.add_argument(
        "--width",
        type=_positive_int,
        default=default_width,
        help=T("aide.width_max"),
    )
    parser.add_argument(
        "--height", type=_positive_int, help=T("aide.height_max")
    )
    parser.add_argument(
        "--fit",
        choices=FIT_MODES,
        default="contain",
        help=T("aide.fit"),
    )
    parser.add_argument(
        "--char-aspect",
        type=_char_aspect,
        help=T("aide.char_aspect"),
    )


def _add_record_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--record",
        type=Path,
        metavar="PATH",
        help=T("aide.record"),
    )
    parser.add_argument(
        "--font", type=Path, help=T("aide.font_record")
    )
    parser.add_argument(
        "--font-size",
        type=_positive_int,
        default=16,
        help=T("aide.font_size"),
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
            print(T("enreg.images", nombre=recorder.frames, chemin=recorder.destination))


class _FrenchHelpFormatter(argparse.HelpFormatter):
    """Remplace le préfixe « usage: », qu'argparse ne rend pas configurable."""

    def add_usage(self, usage, actions, groups, prefix=None):
        # Tester None, pas la valeur de vérité : argparse appelle add_usage avec
        # un préfixe vide pour calculer le « prog » des sous-commandes.
        if prefix is None:
            prefix = T("argparse.utilisation")
        super().add_usage(usage, actions, groups, prefix)


def _localize(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Francise les libellés qu'argparse produit lui-même.

    argparse fait passer ses propres textes par gettext et CPython ne livre
    aucun catalogue français ; les titres de sections ne sont joignables que par
    ces attributs, privés mais stables depuis Python 3. Les parseurs sont créés
    avec ``add_help=False`` pour que ``-h`` soit déclaré ici, en premier, avec
    un texte traduit.
    """
    parser._positionals.title = T("argparse.positionnels")
    parser._optionals.title = T("argparse.options")
    parser.add_argument(
        "-h", "--help", action="help", help=T("aide.aide")
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
            description=T("aide.programme"),
            add_help=False,
            formatter_class=_FrenchHelpFormatter,
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=T("aide.version"),
    )
    parser.add_argument(
        "--lang",
        type=_langue,
        default=langue(),
        choices=(*LANGUES, "auto"),
        help=T("aide.langue"),
    )
    # Non obligatoire : « hachure » tout court ouvre le menu interactif.
    subparsers = parser.add_subparsers(dest="command")

    menu_parser = _subparser(
        subparsers, "menu", help=T("aide.cmd_menu")
    )
    menu_parser.set_defaults(handler=_run_menu)

    list_parser = _subparser(subparsers, "list", help=T("aide.cmd_list"))
    list_parser.set_defaults(handler=_run_list)

    doctor_parser = _subparser(
        subparsers, "doctor", help=T("aide.cmd_doctor")
    )
    doctor_parser.set_defaults(handler=_run_doctor)

    calibrate_parser = _subparser(
        subparsers, "calibrate", help=T("aide.cmd_calibrate")
    )
    calibrate_parser.add_argument(
        "--font", type=Path, help=T("aide.font_mesurer")
    )
    calibrate_parser.add_argument(
        "--length",
        type=_positive_int,
        default=12,
        help=T("aide.length"),
    )
    calibrate_parser.add_argument(
        "--size",
        type=_positive_int,
        default=32,
        help=T("aide.size_mesure"),
    )
    calibrate_parser.set_defaults(handler=_run_calibrate)

    image_parser = _subparser(subparsers, "image", help=T("aide.cmd_image"))
    image_parser.add_argument("path", type=Path, help=T("aide.chemin_image"))
    _add_geometry_options(image_parser, default_width=100)
    _add_style_options(image_parser, default_color=False)
    image_parser.add_argument(
        "-o", "--output", type=Path, help=T("aide.output")
    )
    image_parser.set_defaults(handler=_run_image)

    video_parser = _subparser(subparsers, "video", help=T("aide.cmd_video"))
    video_parser.add_argument("path", type=Path, help=T("aide.chemin_video"))
    _add_geometry_options(video_parser, default_width=160)
    _add_style_options(video_parser, default_color=False)
    _add_playback_options(video_parser)
    _add_record_options(video_parser)
    video_parser.add_argument(
        "--loop", action="store_true", help=T("aide.loop")
    )
    video_parser.add_argument(
        "--start",
        type=_nonnegative_float,
        default=0.0,
        help=T("aide.start"),
    )
    video_parser.add_argument(
        "--duration", type=_positive_float, help=T("aide.duration")
    )
    video_parser.add_argument(
        "--no-audio", action="store_true", help=T("aide.no_audio")
    )
    video_parser.add_argument(
        "--audio-delay",
        type=_audio_delay,
        default=0.0,
        help=T("aide.audio_delay"),
    )
    video_parser.set_defaults(handler=_run_video)

    camera_parser = _subparser(subparsers, "camera", help=T("aide.cmd_camera"))
    camera_parser.add_argument("--device", help=T("aide.device"))
    camera_parser.add_argument(
        "--list", action="store_true", help=T("aide.list_cameras")
    )
    camera_parser.add_argument(
        "--size", help=T("aide.size_capture")
    )
    camera_parser.add_argument(
        "--duration", type=_positive_float, help=T("aide.duration")
    )
    _add_geometry_options(camera_parser, default_width=160)
    _add_style_options(camera_parser, default_color=True)
    _add_playback_options(camera_parser, default_fps=15.0)
    _add_record_options(camera_parser)
    camera_parser.set_defaults(handler=_run_camera)

    demo_parser = _subparser(subparsers, "demo", help=T("aide.cmd_demo"))
    demo_parser.add_argument("name", choices=sorted(DEMOS), help=T("aide.nom_demo"))
    demo_parser.add_argument("--width", type=_positive_int, help=T("aide.width"))
    demo_parser.add_argument("--height", type=_positive_int, help=T("aide.height"))
    demo_parser.add_argument(
        "--fps",
        type=_positive_float,
        default=30.0,
        help=T("aide.fps"),
    )
    demo_parser.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default=DEFAULT_CHARSET,
        help=T("aide.charset"),
    )
    demo_parser.add_argument(
        "--invert", action="store_true", help=T("aide.invert")
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
        help=T("aide.fps"),
    )
    parser.add_argument(
        "--smoothing",
        type=_unit_float,
        default=1.0,
        help=T("aide.smoothing"),
    )
    parser.add_argument(
        "--max-frame-skip",
        type=_nonnegative_int,
        default=5,
        help=T("aide.max_frame_skip"),
    )


def _run_list(_args: argparse.Namespace) -> int:
    print(T("liste.entrees"))
    for nom, cle in (("image", "liste.image"), ("video", "liste.video"), ("camera", "liste.camera")):
        print(f"  {nom:<10} {T(cle)}")
    print(f"\n{T('liste.demos')}")
    for demo in DEMOS.values():
        print(f"  {demo.name:<10} {demo.description}")
    return 0


def _tool_version(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        return T("doctor.hors_path")
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
            version = getattr(imported, "__version__", T("doctor.inconnu"))
            print(f"{module:<13} {version}")
        except ImportError:
            print(f"{module:<13} {T('doctor.absent')}")

    for tool in ("ffmpeg", "ffplay", "ffprobe"):
        print(f"{tool:<13} {_tool_version(tool)}")

    # Les libellés du terminal changent de longueur selon la langue : on les
    # aligne sur le plus long, et sur les 13 colonnes des lignes précédentes.
    cles = ("doctor.terminal", "doctor.profondeur", "doctor.rapport", "doctor.tty", "doctor.codec")
    largeur = max(13, *(len(T(cle)) for cle in cles))
    valeurs = (
        f"{columns} x {rows} {T('doctor.cellules')}",
        detect_color_depth(),
        default_char_aspect(),
        sys.stdout.isatty(),
        getattr(sys.stdout, "encoding", T("doctor.inconnu")),
    )
    for cle, valeur in zip(cles, valeurs):
        print(f"{T(cle).ljust(largeur)} {valeur}")

    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print(T("doctor.video_manquante", outils=", ".join(missing)))
        return 1
    return 0


def _run_calibrate(args: argparse.Namespace) -> int:
    font = args.font.expanduser().resolve() if args.font else find_monospace_font()
    if font is None:
        raise ValueError(T("erreur.police_absente"))
    if not font.is_file():
        raise ValueError(T("erreur.police_introuvable", chemin=font))

    ramp = calibrate(font, size=args.size, length=args.length)
    largeur = max(len(T("calibrate.police")), len(T("calibrate.rampe")))
    print(f"{T('calibrate.police').ljust(largeur)} : {font}")
    print(f"{T('calibrate.rampe').ljust(largeur)} : {ramp!r}")
    print(T("calibrate.conseil"))
    for name, existing in sorted(CHARSETS.items()):
        print(f"  {name:<10} {existing!r}")
    return 0


def _run_image(args: argparse.Namespace) -> int:
    path = args.path.expanduser().resolve()
    if not path.is_file():
        raise ImageRenderError(T("erreur.image_introuvable", chemin=path))
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
        print(T("image.ecrite", colonnes=columns, lignes=height, chemin=destination))
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
            print(T("camera.aucune"))
            return 1
        print(T("camera.titre"))
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
            stopped_message=T("arret.demo", nom=demo.name.capitalize()),
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


def _langue_demandee(argv: Sequence[str] | None) -> str | None:
    """Cherche --lang dans argv avant que le parseur n'existe.

    L'aide d'argparse est figée à la construction du parseur : la langue doit
    donc être connue avant. On ne fait qu'un repérage grossier — le parseur
    valide ensuite la valeur pour de bon.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    for rang, argument in enumerate(arguments):
        if argument == "--lang" and rang + 1 < len(arguments):
            return arguments[rang + 1]
        if argument.startswith("--lang="):
            return argument.split("=", 1)[1]
    return None


def main(argv: Sequence[str] | None = None) -> int:
    demandee = _langue_demandee(argv)
    if demandee is not None:
        # « auto » redemande une détection ; definir_langue s'en charge sur None.
        definir_langue(None if demandee.strip().lower() == "auto" else demandee)
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
        parser.exit(2, f"{T('erreur.prefixe')}{exc}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
