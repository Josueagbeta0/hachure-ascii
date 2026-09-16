import unittest

from hachure.charsets import (
    CHARSETS,
    DEFAULT_CHARSET,
    brightness_to_char,
    brightness_to_index,
    build_ramp,
    candidate_characters,
    get_charset,
)


class JeuDeCaracteresTests(unittest.TestCase):
    def test_le_jeu_de_caracteres_par_defaut_existe(self) -> None:
        self.assertIn(DEFAULT_CHARSET, CHARSETS)

    def test_chaque_rampe_va_du_vide_au_dense(self) -> None:
        for name, ramp in CHARSETS.items():
            with self.subTest(charset=name):
                self.assertGreater(len(ramp), 1)

    def test_l_inversion_retourne_la_rampe(self) -> None:
        self.assertEqual(
            get_charset("classic", invert=True), CHARSETS["classic"][::-1]
        )

    def test_un_jeu_inconnu_liste_les_choix(self) -> None:
        with self.assertRaisesRegex(ValueError, "classic"):
            get_charset("nope")

    def test_la_luminosite_couvre_toute_la_rampe(self) -> None:
        self.assertEqual(brightness_to_index(0, 10), 0)
        self.assertEqual(brightness_to_index(255, 10), 9)

    def test_une_luminosite_hors_plage_est_bornee(self) -> None:
        self.assertEqual(brightness_to_char(-50, " .#"), " ")
        self.assertEqual(brightness_to_char(999, " .#"), "#")

    def test_une_rampe_vide_est_rejetee(self) -> None:
        with self.assertRaises(ValueError):
            brightness_to_index(128, 0)


class RampeSmoothTests(unittest.TestCase):
    def test_la_rampe_calibree_commence_par_du_vide(self) -> None:
        self.assertTrue(CHARSETS["smooth"].startswith(" "))

    def test_la_rampe_calibree_evite_les_glyphes_de_contour(self) -> None:
        """Les glyphes de ligne sont réservés à l'orientation des contours et doivent rester distincts."""
        for glyph in "-|/\\":
            with self.subTest(glyph=glyph):
                self.assertNotIn(glyph, CHARSETS["smooth"])


class CalibrationTests(unittest.TestCase):
    def test_les_candidats_excluent_les_glyphes_de_ligne_reserves(self) -> None:
        for glyph in "-|/\\":
            with self.subTest(glyph=glyph):
                self.assertNotIn(glyph, candidate_characters())

    def test_une_rampe_est_construite_en_couverture_croissante(self) -> None:
        measurements = {
            "a": (0.10, 0.9),
            "b": (0.20, 0.9),
            "c": (0.30, 0.9),
            "d": (0.40, 0.9),
        }
        ramp = build_ramp(measurements, length=5)

        self.assertEqual(ramp[0], " ")
        coverages = [measurements[character][0] for character in ramp[1:]]
        self.assertEqual(coverages, sorted(coverages))

    def test_l_encre_bien_repartie_emporte_l_egalite(self) -> None:
        measurements = {"x": (0.20, 0.1), "o": (0.20, 0.95), "z": (0.40, 0.5)}
        ramp = build_ramp(measurements, length=3)
        self.assertIn("o", ramp)
        self.assertNotIn("x", ramp)

    def test_une_rampe_exige_deux_caracteres(self) -> None:
        with self.assertRaises(ValueError):
            build_ramp({"a": (0.1, 0.5)}, length=1)

    def test_une_couverture_uniforme_ne_produit_pas_de_rampe(self) -> None:
        with self.assertRaises(ValueError):
            build_ramp({"a": (0.2, 0.5), "b": (0.2, 0.5)}, length=3)

    def test_l_absence_de_mesures_est_une_erreur(self) -> None:
        with self.assertRaises(ValueError):
            build_ramp({}, length=4)


if __name__ == "__main__":
    unittest.main()
