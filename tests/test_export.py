import unittest

from hachure.export import (
    DEFAULT_FOREGROUND,
    ansi256_to_rgb,
    iter_runs,
    strip_ansi,
)


class AnalyseAnsiTests(unittest.TestCase):
    def test_du_texte_brut_forme_une_seule_plage(self) -> None:
        self.assertEqual(
            list(iter_runs("abc")), [(0, "abc", DEFAULT_FOREGROUND, None)]
        )

    def test_le_premier_plan_truecolor_est_retrouve(self) -> None:
        runs = list(iter_runs("\x1b[38;2;10;20;30mab\x1b[0m"))
        self.assertEqual(runs, [(0, "ab", (10, 20, 30), None)])

    def test_les_paires_premier_plan_arriere_plan_sont_retrouvees(self) -> None:
        line = "\x1b[38;2;1;2;3m\x1b[48;2;4;5;6m▀▀\x1b[0m"
        runs = list(iter_runs(line))
        self.assertEqual(runs, [(0, "▀▀", (1, 2, 3), (4, 5, 6))])

    def test_les_colonnes_avancent_d_une_plage_a_l_autre(self) -> None:
        line = "ab\x1b[38;2;9;9;9mcd"
        runs = list(iter_runs(line))
        self.assertEqual([run[0] for run in runs], [0, 2])
        self.assertEqual([run[1] for run in runs], ["ab", "cd"])

    def test_reset_restaure_le_stylo_par_defaut(self) -> None:
        runs = list(iter_runs("\x1b[38;2;1;2;3m\x1b[48;2;4;5;6mx\x1b[0my"))
        self.assertEqual(runs[1], (1, "y", DEFAULT_FOREGROUND, None))

    def test_les_codes_de_palette_sont_developpes(self) -> None:
        runs = list(iter_runs("\x1b[38;5;196mx"))
        self.assertEqual(runs[0][2], ansi256_to_rgb(196))

    def test_strip_ansi_supprime_toutes_les_sequences(self) -> None:
        self.assertEqual(strip_ansi("\x1b[38;2;1;2;3mab\x1b[0m\x1b[0mc"), "abc")


class Ansi256Tests(unittest.TestCase):
    def test_la_rampe_de_gris_est_neutre(self) -> None:
        red, green, blue = ansi256_to_rgb(240)
        self.assertEqual(red, green)
        self.assertEqual(green, blue)

    def test_les_entrees_du_cube_restent_dans_la_plage(self) -> None:
        for index in range(16, 256):
            with self.subTest(index=index):
                for channel in ansi256_to_rgb(index):
                    self.assertGreaterEqual(channel, 0)
                    self.assertLessEqual(channel, 255)


if __name__ == "__main__":
    unittest.main()
