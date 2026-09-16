import unittest

import numpy

from hachure.color import AnsiPalette
from hachure.edges import EDGE_GLYPHS
from hachure.render import (
    EDGE_SUPERSAMPLE,
    LOWER_HALF_BLOCK,
    UPPER_HALF_BLOCK,
    RenderStyle,
    render_array,
)
from hachure.tone import ToneMapper


class StyleDeRenduTests(unittest.TestCase):
    def test_les_cellules_char_utilisent_une_ligne_de_balayage_chacune(self) -> None:
        self.assertEqual(RenderStyle(" .#").pixel_rows(20), 20)

    def test_les_cellules_half_utilisent_deux_lignes_de_balayage_chacune(self) -> None:
        self.assertEqual(RenderStyle(" .#", cell_mode="half").pixel_rows(20), 40)


class RenduMonochromeTests(unittest.TestCase):
    def test_les_extremites_de_luminosite_tombent_aux_bouts_de_la_rampe(self) -> None:
        frame = numpy.array([[0, 128, 255]], dtype=numpy.float32)
        self.assertEqual(render_array(frame, RenderStyle(" .#"), numpy), " .#")

    def test_les_cellules_half_fusionnent_deux_lignes_en_une(self) -> None:
        frame = numpy.array([[0, 255], [0, 255]], dtype=numpy.float32)
        rendered = render_array(frame, RenderStyle(" .#", cell_mode="half"), numpy)
        self.assertEqual(rendered, " #")

    def test_une_forte_arete_verticale_devient_un_glyphe_de_bloc(self) -> None:
        frame = numpy.array([[255], [0]], dtype=numpy.float32)
        rendered = render_array(frame, RenderStyle(" .#", cell_mode="half"), numpy)
        self.assertEqual(rendered, UPPER_HALF_BLOCK)

        frame = numpy.array([[0], [255]], dtype=numpy.float32)
        rendered = render_array(frame, RenderStyle(" .#", cell_mode="half"), numpy)
        self.assertEqual(rendered, LOWER_HALF_BLOCK)

    def test_les_tableaux_couleur_sont_acceptes_en_mode_monochrome(self) -> None:
        frame = numpy.zeros((1, 2, 3), dtype=numpy.float32)
        frame[0, 1] = [255, 255, 255]
        self.assertEqual(render_array(frame, RenderStyle(" .#"), numpy), " #")


class RenduCouleurTests(unittest.TestCase):
    def test_le_truecolor_emet_une_sequence_de_premier_plan_par_plage(self) -> None:
        frame = numpy.zeros((1, 3, 3), dtype=numpy.float32)
        frame[0, 0] = [255, 0, 0]
        frame[0, 1] = [255, 0, 0]
        frame[0, 2] = [0, 0, 252]

        rendered = render_array(
            frame, RenderStyle(" .#", color_depth="truecolor", quantization=4), numpy
        )

        self.assertEqual(rendered.count("\x1b[38;2;"), 2)
        self.assertIn("\x1b[38;2;252;0;0m", rendered)
        self.assertTrue(rendered.endswith("\x1b[0m"))

    def test_des_voisins_identiques_partagent_une_seule_sequence(self) -> None:
        frame = numpy.full((1, 40, 3), 128, dtype=numpy.float32)
        rendered = render_array(
            frame, RenderStyle(" .#", color_depth="truecolor"), numpy
        )
        self.assertEqual(rendered.count("\x1b[38;2;"), 1)

    def test_les_cellules_half_associent_un_premier_plan_et_un_arriere_plan(self) -> None:
        frame = numpy.zeros((2, 1, 3), dtype=numpy.float32)
        frame[0, 0] = [255, 0, 0]
        frame[1, 0] = [0, 255, 0]

        rendered = render_array(
            frame,
            RenderStyle(" .#", cell_mode="half", color_depth="truecolor"),
            numpy,
        )

        self.assertIn("\x1b[38;2;252;0;0m", rendered)
        self.assertIn("\x1b[48;2;0;252;0m", rendered)
        self.assertIn(UPPER_HALF_BLOCK, rendered)

    def test_chaque_ligne_redonne_sa_couleur(self) -> None:
        """Les lignes doivent être autonomes pour que l'écran puisse les redessiner une par une."""
        frame = numpy.full((2, 2, 3), 200, dtype=numpy.float32)
        rendered = render_array(
            frame, RenderStyle(" .#", color_depth="truecolor"), numpy
        )
        first, second = rendered.split("\n")
        self.assertTrue(second.startswith("\x1b[38;2;"))
        self.assertTrue(first.endswith("\x1b[0m"))

    def test_ansi256_utilise_la_forme_palette(self) -> None:
        frame = numpy.full((1, 1, 3), 255, dtype=numpy.float32)
        rendered = render_array(
            frame, RenderStyle(" .#", color_depth="ansi256"), numpy
        )
        self.assertIn("\x1b[38;5;", rendered)

    def test_le_rendu_couleur_exige_une_entree_rvb(self) -> None:
        frame = numpy.zeros((2, 2), dtype=numpy.float32)
        with self.assertRaises(ValueError):
            render_array(frame, RenderStyle(" .#", color_depth="truecolor"), numpy)


class IntegrationDesContoursTests(unittest.TestCase):
    def _style(self, **overrides) -> RenderStyle:
        return RenderStyle(" .#", edges=True, edge_strength=0.3, **overrides)

    def test_les_contours_reclament_une_source_surechantillonnee(self) -> None:
        style = self._style()
        self.assertEqual(style.supersample, EDGE_SUPERSAMPLE)
        self.assertEqual(style.pixel_cols(20), 20 * EDGE_SUPERSAMPLE)
        self.assertEqual(style.pixel_rows(10), 10 * EDGE_SUPERSAMPLE)

    def test_les_cellules_half_ignorent_les_contours(self) -> None:
        """Une demi-cellule dessine toujours le même glyphe : l'orientation n'y a aucun sens."""
        style = RenderStyle(" .#", cell_mode="half", edges=True)
        self.assertFalse(style.edges_active)
        self.assertEqual(style.supersample, 1)
        self.assertEqual(style.alphabet, " .#")

    def test_l_alphabet_ajoute_les_glyphes_de_contour(self) -> None:
        self.assertEqual(self._style().alphabet, " .#" + "".join(EDGE_GLYPHS))

    def test_un_contour_vertical_produit_des_barres_verticales(self) -> None:
        size = EDGE_SUPERSAMPLE * 6
        frame = numpy.zeros((size, size), dtype=numpy.float32)
        frame[:, : size // 2] = 255.0

        rendered = render_array(frame, self._style(), numpy)

        self.assertIn("|", rendered)

    def test_une_image_plate_n_affiche_jamais_de_glyphe_de_contour(self) -> None:
        size = EDGE_SUPERSAMPLE * 6
        frame = numpy.full((size, size), 120.0, dtype=numpy.float32)

        rendered = render_array(frame, self._style(), numpy)

        for glyph in EDGE_GLYPHS:
            with self.subTest(glyph=glyph):
                self.assertNotIn(glyph, rendered)

    def test_la_grille_correspond_au_nombre_de_cellules_demande(self) -> None:
        cols, rows = 7, 5
        style = self._style()
        frame = numpy.zeros(
            (style.pixel_rows(rows), style.pixel_cols(cols)), dtype=numpy.float32
        )
        frame[:, : style.pixel_cols(cols) // 2] = 255.0

        lines = render_array(frame, style, numpy).split("\n")

        self.assertEqual(len(lines), rows)
        self.assertTrue(all(len(line) == cols for line in lines))

    def test_les_glyphes_de_contour_survivent_au_chemin_couleur(self) -> None:
        size = EDGE_SUPERSAMPLE * 6
        frame = numpy.zeros((size, size, 3), dtype=numpy.float32)
        frame[:, : size // 2] = [255.0, 255.0, 255.0]

        rendered = render_array(frame, self._style(color_depth="truecolor"), numpy)

        self.assertIn("|", rendered)
        self.assertIn("\x1b[38;2;", rendered)


class IntegrationTonaleTests(unittest.TestCase):
    def test_les_niveaux_automatiques_atteignent_le_bout_dense_de_la_rampe(self) -> None:
        frame = numpy.linspace(60.0, 90.0, 64).reshape(8, 8).astype(numpy.float32)
        style = RenderStyle(" .:-=+*#%@")

        plain = render_array(frame, style, numpy)
        stretched = render_array(
            frame, style, numpy, tone=ToneMapper(auto_levels=True)
        )

        self.assertNotIn("@", plain)
        self.assertIn("@", stretched)

    def test_la_tonalite_preserve_la_teinte_sur_une_entree_couleur(self) -> None:
        frame = numpy.zeros((1, 1, 3), dtype=numpy.float32)
        frame[0, 0] = [80.0, 40.0, 20.0]
        style = RenderStyle(" .#", color_depth="truecolor", quantization=1)

        rendered = render_array(frame, style, numpy, tone=ToneMapper(gamma=2.0))

        red, green, blue = (
            int(value)
            for value in rendered.split("\x1b[38;2;")[1].split("m")[0].split(";")
        )
        self.assertGreater(red, 80)
        self.assertAlmostEqual(red / green, 2.0, places=1)
        self.assertAlmostEqual(red / blue, 4.0, places=1)


class PaletteTests(unittest.TestCase):
    def test_les_prefixes_sont_reutilises_d_un_appel_a_l_autre(self) -> None:
        palette = AnsiPalette("truecolor")
        packed = AnsiPalette.pack(1, 2, 3)
        self.assertIs(palette.foreground(packed), palette.foreground(packed))

    def test_une_profondeur_none_ne_produit_aucun_code_d_echappement(self) -> None:
        palette = AnsiPalette("none")
        self.assertEqual(palette.foreground(AnsiPalette.pack(1, 2, 3)), "")


if __name__ == "__main__":
    unittest.main()
