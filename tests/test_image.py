import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from hachure.cli import main
from hachure.i18n import T


class CommandeImageTests(unittest.TestCase):
    def test_la_commande_image_accepte_un_chemin_externe_absolu(self) -> None:
        # Le message de succès est traduit : on compare à ce que rend le
        # catalogue dans la langue courante, quelle qu'elle soit.
        with tempfile.TemporaryDirectory() as directory:
            temporary_directory = Path(directory)
            source = temporary_directory / "source image.png"
            destination = temporary_directory / "output" / "image.txt"
            Image.new("L", (2, 2), color=255).save(source)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "image",
                        str(source.resolve()),
                        "--width",
                        "4",
                        "--height",
                        "2",
                        "--output",
                        str(destination),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(destination.read_text(encoding="utf-8"), "@@@@\n@@@@\n")
            attendu = T("image.ecrite", colonnes=4, lignes=2, chemin=destination)
            self.assertIn(attendu, output.getvalue())


if __name__ == "__main__":
    unittest.main()
