import unittest

import numpy

from hachure.edges import EDGE_GLYPHS, block_mean, edge_indices

SCALE = 4
CELLS = 8
SIZE = SCALE * CELLS


def glyph_grid(image, strength=0.3):
    mask, indices = edge_indices(
        image.astype(numpy.float32), SCALE, SCALE, numpy, strength=strength
    )
    glyphs = numpy.array(list(EDGE_GLYPHS))[indices]
    return numpy.where(mask, glyphs, " ")


def marked_glyphs(image, strength=0.3):
    grid = glyph_grid(image, strength)
    return {character for character in grid.reshape(-1).tolist() if character != " "}


class OrientationDesContoursTests(unittest.TestCase):
    def test_un_contour_horizontal_se_lit_comme_un_tiret(self) -> None:
        image = numpy.zeros((SIZE, SIZE))
        image[: SIZE // 2] = 255
        self.assertEqual(marked_glyphs(image), {"-"})

    def test_un_contour_vertical_se_lit_comme_une_barre_verticale(self) -> None:
        image = numpy.zeros((SIZE, SIZE))
        image[:, : SIZE // 2] = 255
        self.assertEqual(marked_glyphs(image), {"|"})

    def test_une_diagonale_descendante_se_lit_comme_une_contre_oblique(self) -> None:
        y, x = numpy.mgrid[0:SIZE, 0:SIZE]
        self.assertEqual(marked_glyphs(numpy.where(y > x, 255, 0)), {"\\"})

    def test_une_diagonale_montante_se_lit_comme_une_oblique(self) -> None:
        y, x = numpy.mgrid[0:SIZE, 0:SIZE]
        image = numpy.where(y > (SIZE - 1 - x), 255, 0)
        self.assertEqual(marked_glyphs(image), {"/"})


class SelectiviteDesContoursTests(unittest.TestCase):
    def test_une_image_plate_n_a_aucun_contour(self) -> None:
        mask, _ = edge_indices(
            numpy.full((SIZE, SIZE), 128.0), SCALE, SCALE, numpy, strength=0.3
        )
        self.assertEqual(int(mask.sum()), 0)

    def test_une_image_noire_n_a_aucun_contour(self) -> None:
        mask, _ = edge_indices(
            numpy.zeros((SIZE, SIZE)), SCALE, SCALE, numpy, strength=0.3
        )
        self.assertEqual(int(mask.sum()), 0)

    def test_augmenter_la_force_marque_moins_de_cellules(self) -> None:
        rng = numpy.random.default_rng(7)
        image = rng.integers(0, 255, size=(SIZE, SIZE)).astype(numpy.float32)
        image[:, : SIZE // 2] += 400

        low, _ = edge_indices(image, SCALE, SCALE, numpy, strength=0.1)
        high, _ = edge_indices(image, SCALE, SCALE, numpy, strength=0.9)

        self.assertGreaterEqual(int(low.sum()), int(high.sum()))

    def test_le_resultat_couvre_la_grille_de_cellules(self) -> None:
        image = numpy.zeros((SIZE, SIZE))
        image[:, : SIZE // 2] = 255
        mask, indices = edge_indices(image, SCALE, SCALE, numpy)
        self.assertEqual(mask.shape, (CELLS, CELLS))
        self.assertEqual(indices.shape, (CELLS, CELLS))


class MoyenneParBlocTests(unittest.TestCase):
    def test_un_bloc_unitaire_renvoie_l_entree(self) -> None:
        array = numpy.arange(12.0).reshape(3, 4)
        numpy.testing.assert_array_equal(block_mean(array, 1, 1, numpy), array)

    def test_chaque_tuile_est_moyennee(self) -> None:
        array = numpy.array([[0.0, 0.0, 4.0, 4.0], [2.0, 2.0, 8.0, 8.0]])
        numpy.testing.assert_allclose(
            block_mean(array, 2, 2, numpy), numpy.array([[1.0, 6.0]])
        )

    def test_les_canaux_de_couleur_survivent_a_la_moyenne(self) -> None:
        array = numpy.zeros((2, 2, 3))
        array[..., 0] = 10.0
        result = block_mean(array, 2, 2, numpy)
        self.assertEqual(result.shape, (1, 1, 3))
        self.assertAlmostEqual(float(result[0, 0, 0]), 10.0)

    def test_une_tuile_finale_incomplete_est_abandonnee(self) -> None:
        array = numpy.ones((5, 5))
        self.assertEqual(block_mean(array, 2, 2, numpy).shape, (2, 2))


if __name__ == "__main__":
    unittest.main()
