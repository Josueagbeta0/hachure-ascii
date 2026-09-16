import io
import unittest
from unittest import mock

from hachure.terminal import (
    CHAR_ASPECT_ENV,
    Screen,
    default_char_aspect,
    fit_demo_size,
    fit_source_size,
    source_crop,
)


class DimensionnementTerminalTests(unittest.TestCase):
    def test_le_rapport_de_la_source_tient_compte_des_cellules(self) -> None:
        self.assertEqual(
            fit_source_size(1920, 1080, max_width=100, available=(120, 40)),
            (100, 28),
        )

    def test_la_source_est_reduite_quand_la_hauteur_du_terminal_est_juste(self) -> None:
        self.assertEqual(fit_source_size(1920, 1080, available=(80, 10)), (28, 8))

    def test_un_rapport_de_cellule_plus_large_donne_plus_de_lignes(self) -> None:
        narrow = fit_source_size(
            1920, 1080, max_width=100, available=(120, 60), char_aspect=0.5
        )
        wide = fit_source_size(
            1920, 1080, max_width=100, available=(120, 60), char_aspect=0.6
        )
        self.assertGreater(wide[1], narrow[1])

    def test_l_ajustement_cover_occupe_toute_la_zone_disponible(self) -> None:
        self.assertEqual(
            fit_source_size(1080, 1920, available=(120, 40), fit="cover"),
            (118, 38),
        )

    def test_une_demo_utilise_ses_defauts_dans_les_limites_du_terminal(self) -> None:
        self.assertEqual(
            fit_demo_size(default_width=80, height_ratio=0.44, available=(120, 50)),
            (80, 35),
        )

    def test_une_demo_respecte_les_dimensions_explicites(self) -> None:
        self.assertEqual(
            fit_demo_size(
                default_width=80,
                height_ratio=0.44,
                width=60,
                height=20,
                available=(120, 50),
            ),
            (60, 20),
        )


class RapportDesCellulesTests(unittest.TestCase):
    def test_l_environnement_peut_surcharger_le_rapport_de_cellule(self) -> None:
        with mock.patch.dict("os.environ", {CHAR_ASPECT_ENV: "0.62"}):
            self.assertAlmostEqual(default_char_aspect(), 0.62)

    def test_des_valeurs_absurdes_retombent_sur_le_defaut(self) -> None:
        for value in ("abc", "0", "9"):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {CHAR_ASPECT_ENV: value}):
                    self.assertAlmostEqual(default_char_aspect(), 0.5)


class RecadrageSourceTests(unittest.TestCase):
    def test_une_source_en_portrait_perd_son_haut_et_son_bas(self) -> None:
        width, height, x, y = source_crop(1080, 1920, 100, 28, char_aspect=0.5)
        self.assertEqual(width, 1080)
        self.assertLess(height, 1920)
        self.assertEqual(x, 0)
        self.assertGreater(y, 0)

    def test_une_source_large_perd_ses_cotes(self) -> None:
        width, height, x, y = source_crop(3840, 1080, 40, 40, char_aspect=0.5)
        self.assertLess(width, 3840)
        self.assertEqual(height, 1080)
        self.assertGreater(x, 0)
        self.assertEqual(y, 0)

    def test_le_recadrage_ne_sort_jamais_de_la_source(self) -> None:
        width, height, x, y = source_crop(640, 480, 200, 10, char_aspect=0.5)
        self.assertLessEqual(x + width, 640)
        self.assertLessEqual(y + height, 480)


class EcranTests(unittest.TestCase):
    def _draw(self, screen: Screen, frame: str) -> str:
        buffer = io.StringIO()
        with mock.patch("hachure.terminal.sys.stdout", buffer):
            with mock.patch(
                "hachure.terminal.terminal_size", return_value=(80, 24)
            ):
                screen.draw(frame)
        return buffer.getvalue()

    def test_la_premiere_image_peint_toutes_les_lignes(self) -> None:
        screen = Screen()
        output = self._draw(screen, "ab\ncd")
        self.assertIn("ab", output)
        self.assertIn("cd", output)

    def test_une_image_identique_n_ecrit_rien(self) -> None:
        screen = Screen()
        self._draw(screen, "ab\ncd")
        self.assertEqual(self._draw(screen, "ab\ncd"), "")

    def test_seule_la_ligne_modifiee_est_repeinte(self) -> None:
        screen = Screen()
        self._draw(screen, "ab\ncd")
        output = self._draw(screen, "ab\nXY")
        self.assertIn("XY", output)
        self.assertNotIn("ab", output)

    def test_une_image_plus_courte_efface_les_lignes_restantes(self) -> None:
        screen = Screen()
        self._draw(screen, "a\nb\nc")
        output = self._draw(screen, "a")
        self.assertIn("\x1b[2;1H\x1b[K", output)
        self.assertIn("\x1b[3;1H\x1b[K", output)

    def test_invalidate_force_un_repeint_complet(self) -> None:
        screen = Screen()
        self._draw(screen, "ab\ncd")
        screen.invalidate()
        output = self._draw(screen, "ab\ncd")
        self.assertIn("ab", output)

    def test_un_redimensionnement_force_un_repeint_complet(self) -> None:
        screen = Screen()
        self._draw(screen, "ab")
        buffer = io.StringIO()
        with mock.patch("hachure.terminal.sys.stdout", buffer):
            with mock.patch(
                "hachure.terminal.terminal_size", return_value=(100, 30)
            ):
                screen.draw("ab")
        self.assertIn("ab", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
