import unittest

from hachure.charsets import get_charset
from hachure.renderers import DEMOS


class ContratDesMoteursTests(unittest.TestCase):
    def test_chaque_demo_renvoie_la_taille_d_image_demandee(self) -> None:
        ramp = get_charset("classic")
        for name, demo in DEMOS.items():
            with self.subTest(demo=name):
                frame = demo.render(3, 32, 14, ramp)
                lines = frame.split("\n")
                self.assertEqual(len(lines), 14)
                self.assertTrue(all(len(line) == 32 for line in lines))

    def test_le_cube_contient_une_surface_visible(self) -> None:
        frame = DEMOS["cube"].render(0, 40, 18, get_charset("classic"))
        self.assertTrue(any(character != " " for character in frame if character != "\n"))


if __name__ == "__main__":
    unittest.main()
