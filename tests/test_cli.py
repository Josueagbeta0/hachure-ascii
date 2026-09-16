import contextlib
import io
import unittest
from unittest import mock

from hachure import __version__
from hachure.cli import build_parser, main


class CliTests(unittest.TestCase):
    def test_l_option_version_affiche_la_version_du_paquet(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"hachure {__version__}")

    def test_la_commande_list_decrit_toutes_les_demos(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["list"]), 0)
        for name in ("cube", "sphere", "donut", "planet", "blackhole"):
            self.assertIn(name, output.getvalue())

    def test_les_arguments_video_sont_analyses(self) -> None:
        args = build_parser().parse_args(
            ["video", "movie.mp4", "--color", "--fps", "15", "--no-audio"]
        )
        self.assertTrue(args.color)
        self.assertEqual(args.fps, 15)
        self.assertTrue(args.no_audio)

    def test_l_ancienne_option_mono_prime_sur_color(self) -> None:
        args = build_parser().parse_args(["video", "movie.mp4", "--color", "--mono"])
        self.assertFalse(args.color)

    def test_video_est_monochrome_par_defaut(self) -> None:
        args = build_parser().parse_args(["video", "movie.mp4"])
        self.assertFalse(args.color)

    def test_un_fps_invalide_est_rejete(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["demo", "cube", "--fps", "0"])

    def test_sans_argument_le_menu_est_ouvert(self) -> None:
        with mock.patch("hachure.cli.executer_menu", return_value=0) as menu:
            with mock.patch("hachure.cli.enable_windows_ansi"):
                with mock.patch("hachure.cli.use_utf8_output"):
                    self.assertEqual(main([]), 0)
        menu.assert_called_once()

    def test_la_sous_commande_menu_ouvre_le_meme_menu(self) -> None:
        with mock.patch("hachure.cli.executer_menu", return_value=0) as menu:
            with mock.patch("hachure.cli.enable_windows_ansi"):
                with mock.patch("hachure.cli.use_utf8_output"):
                    self.assertEqual(main(["menu"]), 0)
        menu.assert_called_once()

    def test_un_fps_non_fini_est_rejete(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                    SystemExit
                ):
                    build_parser().parse_args(
                        ["demo", "cube", f"--fps={value}"]
                    )


if __name__ == "__main__":
    unittest.main()
