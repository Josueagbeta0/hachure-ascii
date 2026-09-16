import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hachure.menu import (
    EXTENSIONS_IMAGE,
    EXTENSIONS_POLICE,
    QUITTER,
    Bascule,
    Choix,
    Entree,
    Fichier,
    Sortie,
    _argv_des_champs,
    _contenu,
    _debut_fenetre,
    _entrees_du_dossier,
    _nettoyer_chemin,
    _raccourcir,
    _taille_lisible,
    champs_calibrate,
    champs_demo,
    champs_image,
    champs_video,
    choisir_destination,
    demander_chemin,
    ecran_reglages,
    executer_menu,
    lire_touche,
    noms_proposes,
    parcourir,
    selectionner,
)


@contextlib.contextmanager
def saisies(*lignes: str):
    """Simule des lignes tapées au clavier, hors terminal interactif."""
    entrees = iter(lignes)

    def _input(invite: str = "") -> str:
        try:
            return next(entrees)
        except StopIteration:
            raise EOFError from None

    with mock.patch("hachure.menu.interactif", return_value=False):
        with mock.patch("builtins.input", _input):
            with contextlib.redirect_stdout(io.StringIO()):
                yield


@contextlib.contextmanager
def touches(*noms: str):
    """Simule un terminal interactif piloté par une séquence de touches."""
    suite = iter(noms)

    with mock.patch("hachure.menu.interactif", return_value=True):
        with mock.patch("hachure.menu.lire_touche", lambda: next(suite)):
            with contextlib.redirect_stdout(io.StringIO()):
                yield


class ChampsTests(unittest.TestCase):
    def test_une_bascule_inactive_n_emet_aucun_drapeau(self) -> None:
        self.assertEqual(Bascule("--color", "Couleur").argv(), [])

    def test_une_bascule_active_emet_son_drapeau(self) -> None:
        self.assertEqual(Bascule("--color", "Couleur", actif=True).argv(), ["--color"])

    def test_espace_bascule_dans_les_deux_sens(self) -> None:
        bascule = Bascule("--edges", "Contours")
        bascule.modifier(1)
        self.assertTrue(bascule.actif)
        bascule.modifier(1)
        self.assertFalse(bascule.actif)

    def test_un_choix_tourne_en_boucle(self) -> None:
        choix = Choix("--fit", "Ajustement", ("contain", "cover"))
        choix.modifier(1)
        self.assertEqual(choix.argv(), ["--fit", "cover"])
        choix.modifier(1)
        self.assertEqual(choix.argv(), ["--fit", "contain"])

    def test_un_choix_tourne_aussi_vers_la_gauche(self) -> None:
        choix = Choix("--fit", "Ajustement", ("contain", "cover"))
        choix.modifier(-1)
        self.assertEqual(choix.argv(), ["--fit", "cover"])

    def test_une_valeur_vide_laisse_le_defaut_de_la_cli(self) -> None:
        """Le menu ne doit jamais recopier les valeurs par défaut d'argparse."""
        choix = Choix("--width", "Largeur", ("", "80", "120"))
        self.assertEqual(choix.argv(), [])
        self.assertEqual(choix.affichage(), "défaut")

    def test_une_valeur_choisie_est_emise(self) -> None:
        choix = Choix("--width", "Largeur", ("", "80", "120"))
        choix.modifier(1)
        self.assertEqual(choix.argv(), ["--width", "80"])

    def test_un_fichier_vide_est_omis(self) -> None:
        self.assertEqual(Fichier("--font", "Police").argv(), [])

    def test_un_fichier_affiche_son_nom_pas_son_chemin(self) -> None:
        champ = Fichier("--font", "Police", valeur="C:\\Windows\\Fonts\\consola.ttf")
        self.assertEqual(champ.affichage(), "consola.ttf")

    def test_une_sortie_vide_est_omise(self) -> None:
        self.assertEqual(Sortie("--record", "Enregistrer", (".gif",)).argv(), [])

    def test_une_sortie_renseignee_est_emise(self) -> None:
        champ = Sortie("--record", "Enregistrer", (".gif",), valeur="out\\demo.gif")
        self.assertEqual(champ.argv(), ["--record", "out\\demo.gif"])

    def test_les_champs_sont_concatenes_dans_l_ordre(self) -> None:
        champs = [
            Bascule("--color", "Couleur", actif=True),
            Choix("--fit", "Ajustement", ("contain", "cover"), rang=1),
            Choix("--width", "Largeur", ("", "90"), rang=1),
        ]
        self.assertEqual(
            _argv_des_champs(champs),
            ["--color", "--fit", "cover", "--width", "90"],
        )


class NettoyageDeCheminTests(unittest.TestCase):
    def test_les_guillemets_du_glisser_deposer_sont_retires(self) -> None:
        self.assertEqual(_nettoyer_chemin('  "C:\\a b\\photo.png"  '), "C:\\a b\\photo.png")

    def test_les_apostrophes_sont_retirees_aussi(self) -> None:
        self.assertEqual(_nettoyer_chemin("'photo.png'"), "photo.png")

    def test_un_chemin_nu_est_laisse_tel_quel(self) -> None:
        self.assertEqual(_nettoyer_chemin("photo.png"), "photo.png")

    def test_une_apostrophe_interne_est_preservee(self) -> None:
        self.assertEqual(_nettoyer_chemin("l'image.png"), "l'image.png")


class DemandeDeCheminTests(unittest.TestCase):
    def test_un_fichier_existant_est_accepte(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "photo.png"
            source.write_bytes(b"")
            with saisies(str(source)):
                self.assertEqual(demander_chemin("Chemin"), str(source))

    def test_une_saisie_vide_renonce(self) -> None:
        with saisies(""):
            self.assertIsNone(demander_chemin("Chemin"))

    def test_un_chemin_absent_est_redemande(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "photo.png"
            source.write_bytes(b"")
            with saisies("introuvable.png", str(source)):
                self.assertEqual(demander_chemin("Chemin"), str(source))


class SelectionNumeroteeTests(unittest.TestCase):
    def _entrees(self) -> list[Entree]:
        return [Entree("Un", "un"), Entree("Deux", "deux", "avec détail")]

    def test_un_rang_valide_renvoie_la_valeur(self) -> None:
        with saisies("2"):
            self.assertEqual(selectionner("Titre", self._entrees()), "deux")

    def test_une_saisie_vide_renvoie_none(self) -> None:
        with saisies(""):
            self.assertIsNone(selectionner("Titre", self._entrees()))

    def test_un_rang_hors_plage_est_redemande(self) -> None:
        with saisies("9", "1"):
            self.assertEqual(selectionner("Titre", self._entrees()), "un")

    def test_une_liste_vide_renvoie_none_sans_rien_demander(self) -> None:
        self.assertIsNone(selectionner("Titre", []))


class ReglagesNumerotesTests(unittest.TestCase):
    def test_les_reponses_alimentent_chaque_champ_dans_l_ordre(self) -> None:
        champs = [
            Choix("--width", "Largeur", ("", "64", "80")),
            Bascule("--color", "Couleur"),
            Choix("--fit", "Ajustement", ("contain", "cover")),
        ]
        with saisies("64", "o", "cover"):
            self.assertTrue(ecran_reglages("Titre", champs))
        self.assertEqual(
            _argv_des_champs(champs), ["--width", "64", "--color", "--fit", "cover"]
        )

    def test_le_mot_defaut_ramene_a_la_valeur_vide(self) -> None:
        champs = [Choix("--width", "Largeur", ("", "64"), rang=1)]
        with saisies("défaut"):
            ecran_reglages("Titre", champs)
        self.assertEqual(_argv_des_champs(champs), [])

    def test_une_reponse_negative_laisse_la_bascule_inactive(self) -> None:
        champs = [Bascule("--color", "Couleur", actif=True)]
        with saisies("n"):
            ecran_reglages("Titre", champs)
        self.assertEqual(_argv_des_champs(champs), [])

    def test_une_valeur_hors_liste_laisse_le_choix_inchange(self) -> None:
        champs = [Choix("--fit", "Ajustement", ("contain", "cover"))]
        with saisies("nawak"):
            ecran_reglages("Titre", champs)
        self.assertEqual(_argv_des_champs(champs), ["--fit", "contain"])


class JeuxDeChampsTests(unittest.TestCase):
    def test_les_defauts_de_l_image_donnent_une_commande_lisible(self) -> None:
        self.assertEqual(
            _argv_des_champs(champs_image()),
            ["--fit", "contain", "--edges", "--auto-levels",
             "--charset", "classic", "--cells", "char"],
        )

    def test_aucune_largeur_n_est_imposee_par_defaut(self) -> None:
        """--width doit rester au défaut d'argparse tant qu'on n'y touche pas."""
        self.assertNotIn("--width", _argv_des_champs(champs_image()))

    def test_la_video_active_la_couleur_par_defaut(self) -> None:
        self.assertIn("--color", _argv_des_champs(champs_video()))

    def test_l_image_n_active_pas_la_couleur_par_defaut(self) -> None:
        self.assertNotIn("--color", _argv_des_champs(champs_image()))

    def test_chaque_jeu_de_champs_a_des_drapeaux_uniques(self) -> None:
        for nom, champs in (
            ("image", champs_image()),
            ("video", champs_video()),
            ("demo", champs_demo()),
            ("calibrate", champs_calibrate()),
        ):
            with self.subTest(commande=nom):
                drapeaux = [champ.drapeau for champ in champs]
                self.assertEqual(len(drapeaux), len(set(drapeaux)))

    def test_toute_valeur_numerique_propose_le_defaut_en_tete(self) -> None:
        for nom, champs in (("video", champs_video()), ("demo", champs_demo())):
            for champ in champs:
                if isinstance(champ, Choix) and champ.drapeau in (
                    "--width", "--height", "--fps", "--start", "--duration"
                ):
                    with self.subTest(commande=nom, drapeau=champ.drapeau):
                        self.assertEqual(champ.valeurs[0], "")

    def test_la_base_du_nom_de_sortie_suit_la_source(self) -> None:
        sorties = [c for c in champs_video("clip") if isinstance(c, Sortie)]
        self.assertEqual([c.base for c in sorties], ["clip"])


class NomsProposesTests(unittest.TestCase):
    def test_chaque_extension_donne_un_nom_simple_et_un_nom_horodate(self) -> None:
        noms = noms_proposes("demo", (".gif", ".mp4"))
        self.assertEqual(noms[:2], ["demo.gif", "demo.mp4"])
        self.assertEqual(len(noms), 4)

    def test_les_noms_horodates_portent_leur_extension(self) -> None:
        for nom in noms_proposes("demo", (".gif",))[1:]:
            self.assertTrue(nom.startswith("demo-"))
            self.assertTrue(nom.endswith(".gif"))


class RaccourcissementTests(unittest.TestCase):
    def test_un_texte_court_est_inchange(self) -> None:
        self.assertEqual(_raccourcir("court", 20), "court")

    def test_un_texte_long_est_elide_au_milieu(self) -> None:
        court = _raccourcir("C:\\un\\chemin\\tres\\long\\photo.png", 15)
        self.assertEqual(len(court), 15)
        self.assertIn("…", court)
        self.assertTrue(court.startswith("C:\\un"))
        self.assertTrue(court.endswith(".png"))

    def test_une_largeur_degeneree_ne_leve_pas(self) -> None:
        self.assertEqual(_raccourcir("abcdef", 1), "a")
        self.assertEqual(_raccourcir("abcdef", 0), "")


class FenetreDefilanteTests(unittest.TestCase):
    def test_une_liste_courte_tient_sans_defilement(self) -> None:
        self.assertEqual(_debut_fenetre(0, 5, 10), 0)
        self.assertEqual(_debut_fenetre(4, 5, 10), 0)

    def test_le_curseur_reste_centre_au_milieu(self) -> None:
        self.assertEqual(_debut_fenetre(50, 100, 10), 45)

    def test_la_fenetre_ne_depasse_jamais_les_bords(self) -> None:
        self.assertEqual(_debut_fenetre(0, 100, 10), 0)
        self.assertEqual(_debut_fenetre(99, 100, 10), 90)

    def test_le_curseur_est_toujours_dans_la_fenetre(self) -> None:
        for curseur in range(100):
            debut = _debut_fenetre(curseur, 100, 12)
            with self.subTest(curseur=curseur):
                self.assertTrue(debut <= curseur < debut + 12)


class NavigateurTests(unittest.TestCase):
    @contextlib.contextmanager
    def _arborescence(self):
        with tempfile.TemporaryDirectory() as racine:
            base = Path(racine)
            (base / "sous").mkdir()
            (base / "photo.png").write_bytes(b"x" * 2048)
            (base / "notes.txt").write_text("rien", encoding="utf-8")
            (base / "sous" / "autre.jpg").write_bytes(b"y")
            yield base

    def test_le_contenu_separe_dossiers_et_fichiers_filtres(self) -> None:
        with self._arborescence() as base:
            dossiers, fichiers = _contenu(base, EXTENSIONS_IMAGE)
            self.assertEqual([d.name for d in dossiers], ["sous"])
            self.assertEqual([f.name for f in fichiers], ["photo.png"])

    def test_sans_filtre_tous_les_fichiers_sont_listes(self) -> None:
        with self._arborescence() as base:
            _, fichiers = _contenu(base, None)
            self.assertEqual([f.name for f in fichiers], ["notes.txt", "photo.png"])

    def test_un_dossier_illisible_ne_leve_pas(self) -> None:
        dossiers, fichiers = _contenu(Path("dossier-inexistant-xyz"), None)
        self.assertEqual((dossiers, fichiers), ([], []))

    def test_les_entrees_offrent_le_parent_et_l_annulation(self) -> None:
        with self._arborescence() as base:
            libelles = [
                e.libelle
                for e in _entrees_du_dossier(base, EXTENSIONS_IMAGE, dossier_seulement=False)
            ]
            self.assertIn("..", libelles)
            self.assertIn("sous/", libelles)
            self.assertIn("photo.png", libelles)
            self.assertIn("[ annuler ]", libelles)

    def test_en_mode_dossier_les_fichiers_disparaissent(self) -> None:
        with self._arborescence() as base:
            libelles = [
                e.libelle
                for e in _entrees_du_dossier(base, None, dossier_seulement=True)
            ]
            self.assertIn("[ choisir ce dossier ]", libelles)
            self.assertIn("sous/", libelles)
            self.assertNotIn("photo.png", libelles)

    def test_la_taille_des_fichiers_est_lisible(self) -> None:
        with self._arborescence() as base:
            self.assertEqual(_taille_lisible(base / "photo.png"), "2.0 Ko")

    def test_une_taille_illisible_ne_leve_pas(self) -> None:
        self.assertEqual(_taille_lisible(Path("absent-xyz.png")), "?")

    def test_on_descend_dans_un_dossier_puis_on_choisit_un_fichier(self) -> None:
        with self._arborescence() as base:
            # Entrées : [.., sous/, photo.png, annuler]. On descend dans « sous »
            # puis on prend « autre.jpg », qui s'y trouve seul.
            with touches("bas", "entree", "bas", "entree"):
                choisi = parcourir("Titre", extensions=EXTENSIONS_IMAGE, depart=base)
            self.assertEqual(Path(choisi).name, "autre.jpg")

    def test_annuler_renvoie_none(self) -> None:
        with self._arborescence() as base:
            with touches("echap"):
                self.assertIsNone(parcourir("Titre", depart=base))

    def test_le_mode_dossier_renvoie_le_dossier_courant(self) -> None:
        with self._arborescence() as base:
            with touches("entree"):
                choisi = parcourir("Titre", dossier_seulement=True, depart=base)
            self.assertEqual(Path(choisi).name, base.name)

    def test_une_destination_combine_dossier_et_nom_propose(self) -> None:
        with self._arborescence() as base:
            with mock.patch("hachure.menu._depart", return_value=base):
                # « choisir ce dossier », puis le premier nom propose.
                with touches("entree", "entree"):
                    chemin = choisir_destination("Enregistrer", "demo", (".gif",))
            self.assertEqual(Path(chemin).name, "demo.gif")
            self.assertEqual(Path(chemin).parent, base)


class BomDePowerShellTests(unittest.TestCase):
    """PowerShell prefixe un BOM UTF-8 a tout stdin redirige."""

    def test_un_rang_prefixe_d_un_bom_est_accepte(self) -> None:
        with saisies("\ufeff2"):
            self.assertEqual(
                selectionner("Titre", [Entree("Un", "un"), Entree("Deux", "deux")]),
                "deux",
            )

    def test_un_chemin_prefixe_d_un_bom_est_accepte(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "photo.png"
            source.write_bytes(b"")
            with saisies("\ufeff" + str(source)):
                self.assertEqual(demander_chemin("Chemin"), str(source))

    def test_une_valeur_prefixee_d_un_bom_est_acceptee(self) -> None:
        champs = [Choix("--width", "Largeur", ("", "120"))]
        with saisies("\ufeff120"):
            ecran_reglages("Titre", champs)
        self.assertEqual(_argv_des_champs(champs), ["--width", "120"])


class NavigationAuxFlechesTests(unittest.TestCase):
    def _entrees(self) -> list[Entree]:
        return [Entree("Un", "un"), Entree("Deux", "deux"), Entree("Trois", "trois")]

    def test_bas_descend_dans_la_liste(self) -> None:
        with touches("bas", "bas", "entree"):
            self.assertEqual(selectionner("Titre", self._entrees()), "trois")

    def test_haut_depuis_le_premier_rang_boucle_au_dernier(self) -> None:
        with touches("haut", "entree"):
            self.assertEqual(selectionner("Titre", self._entrees()), "trois")

    def test_bas_depuis_le_dernier_rang_boucle_au_premier(self) -> None:
        with touches("bas", "bas", "bas", "entree"):
            self.assertEqual(selectionner("Titre", self._entrees()), "un")

    def test_echap_renonce_a_la_selection(self) -> None:
        with touches("bas", "echap"):
            self.assertIsNone(selectionner("Titre", self._entrees()))

    def test_une_touche_inconnue_ne_deplace_rien(self) -> None:
        with touches("z", "entree"):
            self.assertEqual(selectionner("Titre", self._entrees()), "un")

    def test_le_bloc_est_repeint_sur_place(self) -> None:
        """Chaque redessin remonte du nombre exact de lignes deja ecrites."""
        suite = iter(["bas", "entree"])
        tampon = io.StringIO()
        with mock.patch("hachure.menu.interactif", return_value=True):
            with mock.patch("hachure.menu.lire_touche", lambda: next(suite)):
                with contextlib.redirect_stdout(tampon):
                    selectionner("Titre", self._entrees())
        rendu = tampon.getvalue()
        # Deux dessins, plus l'effacement final : trois nettoyages de zone.
        self.assertEqual(rendu.count("[J"), 3)
        # Entre les deux dessins, le curseur remonte d'exactement autant de
        # lignes que le premier bloc en comptait.
        premier = rendu.split("[J")[1]
        self.assertIn(f"[{premier.count(chr(10))}A", rendu)

class ReglagesAuxFlechesTests(unittest.TestCase):
    def _champs(self) -> list[Bascule | Choix]:
        return [Bascule("--color", "Couleur"), Choix("--fit", "Ajustement", ("contain", "cover"))]

    def test_espace_bascule_la_ligne_courante(self) -> None:
        champs = self._champs()
        with touches(" ", "bas", "bas", "entree"):
            self.assertTrue(ecran_reglages("Titre", champs))
        self.assertEqual(_argv_des_champs(champs), ["--color", "--fit", "contain"])

    def test_droite_fait_tourner_un_choix(self) -> None:
        champs = self._champs()
        with touches("bas", "droite", "bas", "entree"):
            self.assertTrue(ecran_reglages("Titre", champs))
        self.assertEqual(_argv_des_champs(champs), ["--fit", "cover"])

    def test_la_ligne_annuler_ne_lance_pas_le_rendu(self) -> None:
        with touches("bas", "bas", "bas", "entree"):
            self.assertFalse(ecran_reglages("Titre", self._champs()))

    def test_echap_ne_lance_pas_le_rendu(self) -> None:
        with touches("echap"):
            self.assertFalse(ecran_reglages("Titre", self._champs()))

    def test_entree_sur_un_choix_ouvre_la_liste_complete(self) -> None:
        champs = [Choix("--charset", "Jeu", ("classic", "detailed", "smooth"))]
        # Entrée ouvre la sous-liste, on y descend de deux rangs, on valide,
        # puis on redescend sur « Lancer ».
        with touches("entree", "bas", "bas", "entree", "bas", "entree"):
            self.assertTrue(ecran_reglages("Titre", champs))
        self.assertEqual(_argv_des_champs(champs), ["--charset", "smooth"])

    def test_le_menu_complet_se_parcourt_aux_fleches(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with touches("bas", "bas", "bas", "bas", "entree", "haut", "entree"):
            executer_menu(lanceur)
        lanceur.assert_called_once_with(["doctor"])


class LectureDeToucheTests(unittest.TestCase):
    def test_les_fleches_windows_arrivent_en_deux_temps(self) -> None:
        with mock.patch("hachure.menu.sys.platform", "win32"):
            with mock.patch.dict(
                "sys.modules", {"msvcrt": mock.Mock(getwch=mock.Mock(side_effect=["\xe0", "H"]))}
            ):
                self.assertEqual(lire_touche(), "haut")

    def test_entree_est_reconnue_sous_windows(self) -> None:
        with mock.patch("hachure.menu.sys.platform", "win32"):
            with mock.patch.dict(
                "sys.modules", {"msvcrt": mock.Mock(getwch=mock.Mock(return_value="\r"))}
            ):
                self.assertEqual(lire_touche(), "entree")

    def test_echap_est_reconnu_sous_windows(self) -> None:
        with mock.patch("hachure.menu.sys.platform", "win32"):
            with mock.patch.dict(
                "sys.modules", {"msvcrt": mock.Mock(getwch=mock.Mock(return_value="\x1b"))}
            ):
                self.assertEqual(lire_touche(), "echap")


class BoucleDuMenuTests(unittest.TestCase):
    def test_quitter_sort_sans_rien_lancer(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with saisies("8"):
            self.assertEqual(executer_menu(lanceur), 0)
        lanceur.assert_not_called()

    def test_une_entree_vide_sort_aussi(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with saisies(""):
            self.assertEqual(executer_menu(lanceur), 0)
        lanceur.assert_not_called()

    def test_le_diagnostic_lance_la_commande_doctor(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with saisies("5"):
            executer_menu(lanceur)
        lanceur.assert_called_once_with(["doctor"])

    def test_la_liste_lance_la_commande_list(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with saisies("6"):
            executer_menu(lanceur)
        lanceur.assert_called_once_with(["list"])

    def test_le_code_de_sortie_de_la_commande_est_propage(self) -> None:
        lanceur = mock.Mock(return_value=2)
        with saisies("5"):
            self.assertEqual(executer_menu(lanceur), 2)

    def test_renoncer_au_chemin_ramene_au_menu_sans_lancer(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with saisies("1", "", "8"):
            executer_menu(lanceur)
        lanceur.assert_not_called()

    def test_une_demo_compose_son_nom_et_ses_reglages(self) -> None:
        lanceur = mock.Mock(return_value=0)
        # Menu, démo « cube », puis les six réglages de demo dans l'ordre.
        with saisies("4", "1", "100", "", "24", "detailed", "n", ""):
            executer_menu(lanceur)
        lanceur.assert_called_once_with(
            ["demo", "cube", "--width", "100", "--fps", "24", "--charset", "detailed"]
        )

    def test_une_image_compose_son_chemin_et_ses_reglages(self) -> None:
        lanceur = mock.Mock(return_value=0)
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "photo.png"
            source.write_bytes(b"")
            with saisies("1", str(source), "80", "", "cover", "o", "o", "n",
                         "smooth", "half", "n", ""):
                executer_menu(lanceur)
        lanceur.assert_called_once_with(
            ["image", str(source), "--width", "80", "--fit", "cover",
             "--color", "--edges", "--charset", "smooth", "--cells", "half"]
        )


class ArgvComposeTests(unittest.TestCase):
    """Toute commande composee doit etre acceptee par le parseur reel."""

    def _argv_composes(self) -> list[list[str]]:
        appels: list[list[str]] = []
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / "media.png"
            source.write_bytes(b"")
            scenarios = (
                ("5",),
                ("6",),
                ("4", "1", "", "", "", "", "n", ""),
                ("1", str(source), "", "", "", "n", "n", "n", "", "", "n", ""),
                ("2", str(source), "", "", "", "n", "n", "n", "", "", "n",
                 "", "n", "n", "", "", ""),
                ("7", "", "", ""),
            )
            for lignes in scenarios:
                lanceur = mock.Mock(return_value=0)
                with saisies(*lignes):
                    executer_menu(lanceur)
                appels += [appel.args[0] for appel in lanceur.call_args_list]
        return appels

    def test_le_parseur_accepte_chaque_commande_composee(self) -> None:
        from hachure.cli import build_parser

        argvs = self._argv_composes()
        self.assertEqual(len(argvs), 6)
        for argv in argvs:
            with self.subTest(argv=argv):
                arguments = build_parser().parse_args(argv)
                self.assertEqual(arguments.command, argv[0])
                self.assertTrue(callable(arguments.handler))

    def test_la_valeur_de_sortie_n_est_pas_un_nom_de_commande(self) -> None:
        self.assertNotIn(
            QUITTER, ("image", "video", "camera", "demo", "list", "doctor", "calibrate")
        )


class PoliceTests(unittest.TestCase):
    def test_le_champ_police_filtre_les_extensions_de_police(self) -> None:
        champ = [c for c in champs_calibrate() if isinstance(c, Fichier)][0]
        self.assertEqual(champ.extensions, EXTENSIONS_POLICE)


if __name__ == "__main__":
    unittest.main()
