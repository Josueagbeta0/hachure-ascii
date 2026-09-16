import unittest

import numpy

from hachure.tone import ToneMapper, apply_gamma


class GammaTests(unittest.TestCase):
    def test_un_gamma_de_un_ne_change_rien(self) -> None:
        values = numpy.array([0.0, 128.0, 255.0])
        numpy.testing.assert_array_equal(apply_gamma(values, 1.0, numpy), values)

    def test_un_gamma_superieur_a_un_eclaircit_les_tons_moyens(self) -> None:
        values = numpy.array([128.0])
        self.assertGreater(apply_gamma(values, 2.0, numpy)[0], 128.0)

    def test_un_gamma_inferieur_a_un_assombrit_les_tons_moyens(self) -> None:
        values = numpy.array([128.0])
        self.assertLess(apply_gamma(values, 0.5, numpy)[0], 128.0)

    def test_les_extremites_sont_preservees(self) -> None:
        values = numpy.array([0.0, 255.0])
        result = apply_gamma(values, 2.2, numpy)
        self.assertAlmostEqual(result[0], 0.0)
        self.assertAlmostEqual(result[1], 255.0, places=3)


class NiveauxAutomatiquesTests(unittest.TestCase):
    def test_une_plage_etroite_est_etiree_sur_toute_la_rampe(self) -> None:
        mapper = ToneMapper(auto_levels=True)
        frame = numpy.linspace(80.0, 140.0, 400).reshape(20, 20)

        result = mapper.apply(frame, numpy)

        self.assertLess(result.min(), 20.0)
        self.assertGreater(result.max(), 235.0)

    def test_une_image_plate_est_laissee_telle_quelle(self) -> None:
        mapper = ToneMapper(auto_levels=True)
        frame = numpy.full((10, 10), 60.0)

        result = mapper.apply(frame, numpy)

        numpy.testing.assert_allclose(result, frame)

    def test_les_niveaux_evoluent_progressivement_entre_les_images(self) -> None:
        mapper = ToneMapper(auto_levels=True, inertia=0.2)
        dim = numpy.linspace(0.0, 60.0, 400).reshape(20, 20)
        bright = numpy.linspace(190.0, 255.0, 400).reshape(20, 20)

        mapper.apply(dim, numpy)
        first_low = mapper._low
        mapper.apply(bright, numpy)

        self.assertIsNotNone(first_low)
        self.assertGreater(mapper._low, first_low)
        # Une seule image ne doit pas tirer le niveau jusqu'à sa nouvelle valeur.
        self.assertLess(mapper._low, 190.0)

    def test_reset_oublie_les_niveaux_lisses(self) -> None:
        mapper = ToneMapper(auto_levels=True)
        mapper.apply(numpy.linspace(0.0, 60.0, 400).reshape(20, 20), numpy)
        mapper.reset()
        self.assertIsNone(mapper._low)

    def test_un_mappeur_inactif_se_declare_comme_tel(self) -> None:
        self.assertFalse(ToneMapper().active)
        self.assertTrue(ToneMapper(auto_levels=True).active)
        self.assertTrue(ToneMapper(gamma=1.4).active)

    def test_des_percentiles_invalides_sont_rejetes(self) -> None:
        with self.assertRaises(ValueError):
            ToneMapper(low_percentile=90.0, high_percentile=10.0)

    def test_une_inertie_invalide_est_rejetee(self) -> None:
        with self.assertRaises(ValueError):
            ToneMapper(inertia=0.0)


if __name__ == "__main__":
    unittest.main()
