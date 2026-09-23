import ast
import contextlib
import glob
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hachure.i18n import (
    CATALOGUE,
    LANGUE_ENV,
    LANGUE_PAR_DEFAUT,
    LANGUES,
    T,
    definir_langue,
    detecter_langue,
    langue,
    normaliser,
)

_CHAMPS = re.compile(r"\{(\w+)\}")


@contextlib.contextmanager
def langue_fixee(code: str | None):
    """Fixe la langue le temps d'un test, puis restaure celle du processus."""
    precedente = langue()
    definir_langue(code)
    try:
        yield
    finally:
        definir_langue(precedente)


def _sources() -> list[tuple[str, ast.Module]]:
    sources = []
    for chemin in glob.glob("hachure/**/*.py", recursive=True):
        if chemin.endswith("i18n.py"):
            continue
        sources.append((chemin, ast.parse(Path(chemin).read_text(encoding="utf-8"))))
    return sources


def cles_appelees() -> dict[str, set[str]]:
    """Relève les clés passées littéralement à T(), avec leurs fichiers."""
    trouvees: dict[str, set[str]] = {}
    for chemin, arbre in _sources():
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            if getattr(noeud.func, "id", None) != "T" or not noeud.args:
                continue
            premier = noeud.args[0]
            if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                trouvees.setdefault(premier.value, set()).add(chemin)
    return trouvees


def cles_citees() -> set[str]:
    """Toute chaîne littérale des sources qui est aussi une clé du catalogue.

    Plus large que :func:`cles_appelees` : certaines clés sont rangées dans des
    tuples — le registre des démos, la table du menu, les lignes de « doctor » —
    et résolues par une variable, pas par un littéral dans l'appel à T().
    """
    citees: set[str] = set()
    for _, arbre in _sources():
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                if noeud.value in CATALOGUE:
                    citees.add(noeud.value)
    return citees


class CatalogueTests(unittest.TestCase):
    def test_chaque_entree_couvre_toutes_les_langues(self) -> None:
        for cle, valeurs in CATALOGUE.items():
            with self.subTest(cle=cle):
                self.assertIsInstance(valeurs, tuple)
                self.assertEqual(len(valeurs), len(LANGUES))

    def test_aucune_traduction_n_est_vide(self) -> None:
        for cle, valeurs in CATALOGUE.items():
            for code, texte in zip(LANGUES, valeurs):
                with self.subTest(cle=cle, langue=code):
                    self.assertTrue(texte.strip())

    def test_les_champs_a_substituer_sont_identiques_entre_langues(self) -> None:
        """Un champ oublié dans une traduction lèverait à l'exécution, pas ici."""
        for cle, (fr, en) in CATALOGUE.items():
            with self.subTest(cle=cle):
                self.assertEqual(set(_CHAMPS.findall(fr)), set(_CHAMPS.findall(en)))

    def test_les_deux_langues_restent_distinctes_sauf_termes_communs(self) -> None:
        """Une entrée identique dans les deux langues est presque toujours un oubli."""
        # Mots qui s'écrivent réellement pareil, ou noms propres et unités.
        attendus = {
            "argparse.options", "doctor.terminal", "champ.fit", "lecture.source",
            "lecture.audio", "lecture.pixels", "menu.dossier", "champ.charset",
        }
        identiques = {cle for cle, (fr, en) in CATALOGUE.items() if fr == en}
        self.assertEqual(identiques - attendus, set())

    def test_le_catalogue_ne_garde_pas_de_pourcentage_orphelin(self) -> None:
        """%(default)s vient d'argparse : les deux langues doivent le porter ensemble."""
        for cle, (fr, en) in CATALOGUE.items():
            with self.subTest(cle=cle):
                self.assertEqual("%(default)s" in fr, "%(default)s" in en)


class ClesUtiliseesTests(unittest.TestCase):
    def test_chaque_cle_appelee_existe_au_catalogue(self) -> None:
        manquantes = {
            cle: sorted(fichiers)
            for cle, fichiers in cles_appelees().items()
            if cle not in CATALOGUE
        }
        self.assertEqual(manquantes, {})

    def test_le_catalogue_ne_garde_pas_de_cle_morte(self) -> None:
        self.assertEqual(set(CATALOGUE) - cles_citees(), set())


class FuitesDansLeMenuTests(unittest.TestCase):
    """Aucun texte français ne doit apparaître dans un écran rendu en anglais.

    Le balayage est construit depuis le catalogue, pas depuis une liste de mots
    écrite à la main : c'est ce qui permet d'attraper un oubli auquel on n'aurait
    pas pensé — les unités de taille de fichier, par exemple.
    """

    def _francais_interdit(self) -> dict[str, str]:
        return {
            fr: cle
            for cle, (fr, en) in CATALOGUE.items()
            if fr != en and len(fr) >= 4 and "{" not in fr
        }

    def _fuites(self, sortie: str) -> list[str]:
        # Bornes de mot : « Diagnostic » est une sous-chaîne de « Diagnostics »,
        # qui est bien la traduction anglaise et non une fuite.
        trouves = set()
        for fr, cle in self._francais_interdit().items():
            motif = r"(?<![^\W\d_])" + re.escape(fr) + r"(?![^\W\d_])"
            if re.search(motif, sortie):
                trouves.add(f"{cle} ({fr!r})")
        return sorted(trouves)

    def _rendre(self, appel, touches_simulees) -> str:
        from hachure import menu

        suite = iter(touches_simulees)
        tampon = io.StringIO()
        with mock.patch("hachure.menu.interactif", return_value=True):
            with mock.patch("hachure.menu.lire_touche", lambda: next(suite, "echap")):
                with contextlib.redirect_stdout(tampon):
                    try:
                        appel()
                    except StopIteration:
                        pass
        return re.sub(r"\[[0-9;]*[A-Za-z]", "", tampon.getvalue())

    def test_aucun_ecran_anglais_ne_laisse_passer_de_francais(self) -> None:
        from hachure import menu

        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            (base / "clips").mkdir()
            (base / "film.mp4").write_bytes(b"x" * 4096)

            ecrans = {
                "menu": (lambda: menu.executer_menu(lambda argv: 0), ["echap"]),
                "navigateur": (
                    lambda: menu.parcourir("W?", extensions=menu.EXTENSIONS_VIDEO, depart=base),
                    ["echap"],
                ),
                "navigateur_dossier": (
                    lambda: menu.parcourir("W?", dossier_seulement=True, depart=base),
                    ["echap"],
                ),
                "reglages_video": (
                    lambda: menu.ecran_reglages("S", menu.champs_video("f")), ["echap"]
                ),
                "reglages_image": (
                    lambda: menu.ecran_reglages("S", menu.champs_image("f")), ["echap"]
                ),
                "reglages_camera": (
                    lambda: menu.ecran_reglages("S", menu.champs_camera()), ["echap"]
                ),
                "reglages_demo": (
                    lambda: menu.ecran_reglages("S", menu.champs_demo("cube")), ["echap"]
                ),
                "calibrate": (menu._composer_calibrate, ["echap"]),
                "choix_demo": (menu._composer_demo, ["echap"]),
            }
            with langue_fixee("en"):
                for nom, (appel, touches_simulees) in ecrans.items():
                    with self.subTest(ecran=nom):
                        fuites = self._fuites(self._rendre(appel, touches_simulees))
                        self.assertEqual(fuites, [])

    def test_la_destination_ne_laisse_pas_passer_de_francais(self) -> None:
        from hachure import menu

        with tempfile.TemporaryDirectory() as dossier:
            base = Path(dossier)
            with langue_fixee("en"), mock.patch("hachure.menu._depart", return_value=base):
                sortie = self._rendre(
                    lambda: menu.choisir_destination("Record", "clip", (".mp4",)),
                    ["entree", "entree"],
                )
            self.assertEqual(self._fuites(sortie), [])


class RenduTests(unittest.TestCase):
    def test_une_cle_inconnue_leve(self) -> None:
        with self.assertRaises(KeyError):
            T("cle.qui.n.existe.pas")

    def test_les_champs_sont_substitues(self) -> None:
        with langue_fixee("fr"):
            self.assertEqual(
                T("erreur.image_introuvable", chemin="a.png"), "Image introuvable : a.png"
            )
        with langue_fixee("en"):
            self.assertEqual(
                T("erreur.image_introuvable", chemin="a.png"), "Image not found: a.png"
            )

    def test_chaque_entree_se_rend_dans_les_deux_langues(self) -> None:
        """Aucune traduction ne doit contenir d'accolade non substituable."""
        for cle, (fr, en) in CATALOGUE.items():
            champs = {nom: "x" for nom in _CHAMPS.findall(fr)}
            for code in LANGUES:
                with self.subTest(cle=cle, langue=code):
                    with langue_fixee(code):
                        self.assertIsInstance(T(cle, **champs), str)


class NormalisationTests(unittest.TestCase):
    def test_une_locale_posix_est_reduite_au_code(self) -> None:
        for brut in ("fr", "FR", "fr_FR", "fr_FR.UTF-8", "fr_BE@euro"):
            with self.subTest(brut=brut):
                self.assertEqual(normaliser(brut), "fr")

    def test_les_noms_longs_de_windows_sont_reconnus(self) -> None:
        self.assertEqual(normaliser("French_France"), "fr")
        self.assertEqual(normaliser("English_United States"), "en")

    def test_une_langue_non_gérée_renvoie_none(self) -> None:
        for brut in ("de_DE", "es", "zh_CN", "", None, "  "):
            with self.subTest(brut=brut):
                self.assertIsNone(normaliser(brut))


class DetectionTests(unittest.TestCase):
    def test_la_variable_du_projet_prime_sur_la_locale(self) -> None:
        with mock.patch.dict("os.environ", {LANGUE_ENV: "en", "LANG": "fr_FR.UTF-8"}):
            self.assertEqual(detecter_langue(), "en")

    def test_la_locale_est_utilisee_sans_variable_de_projet(self) -> None:
        env = {"LANG": "fr_FR.UTF-8"}
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(detecter_langue(), "fr")

    def test_language_prime_sur_lang(self) -> None:
        env = {"LANGUAGE": "en_GB", "LANG": "fr_FR.UTF-8"}
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(detecter_langue(), "en")

    def test_une_locale_non_geree_retombe_sur_le_defaut(self) -> None:
        with mock.patch.dict("os.environ", {"LANG": "de_DE.UTF-8"}, clear=True):
            with mock.patch("hachure.i18n._langue_de_windows", return_value=None):
                self.assertEqual(detecter_langue(), LANGUE_PAR_DEFAUT)

    def test_windows_sert_de_recours_sans_variable(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch("hachure.i18n._langue_de_windows", return_value="fr"):
                self.assertEqual(detecter_langue(), "fr")

    def test_l_identifiant_windows_est_traduit(self) -> None:
        from hachure.i18n import _langue_de_windows

        # 0x040C = français (France), 0x0409 = anglais (États-Unis).
        for langid, attendu in ((0x040C, "fr"), (0x0409, "en"), (0x0407, None)):
            with self.subTest(langid=hex(langid)):
                faux = mock.Mock()
                faux.windll.kernel32.GetUserDefaultUILanguage.return_value = langid
                with mock.patch("hachure.i18n.sys.platform", "win32"):
                    with mock.patch.dict("sys.modules", {"ctypes": faux}):
                        self.assertEqual(_langue_de_windows(), attendu)

    def test_hors_windows_le_recours_ne_repond_rien(self) -> None:
        from hachure.i18n import _langue_de_windows

        with mock.patch("hachure.i18n.sys.platform", "linux"):
            self.assertIsNone(_langue_de_windows())


class DefinitionTests(unittest.TestCase):
    def test_une_valeur_explicite_est_retenue(self) -> None:
        with langue_fixee("en"):
            self.assertEqual(langue(), "en")

    def test_none_relance_la_detection(self) -> None:
        with mock.patch.dict("os.environ", {LANGUE_ENV: "fr"}):
            with langue_fixee(None):
                self.assertEqual(langue(), "fr")

    def test_une_valeur_inconnue_relance_la_detection(self) -> None:
        with mock.patch.dict("os.environ", {LANGUE_ENV: "en"}):
            with langue_fixee("klingon"):
                self.assertEqual(langue(), "en")


if __name__ == "__main__":
    unittest.main()
