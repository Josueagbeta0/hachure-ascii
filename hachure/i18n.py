"""Catalogue bilingue de tout ce que le programme affiche.

Un dictionnaire plutôt que gettext : pas de fichiers ``.mo`` à compiler, pas
d'étape de construction, et le catalogue reste relisible et testable comme
n'importe quelle donnée du projet.

Chaque entrée associe une clé à un couple ``(français, anglais)``. Les champs à
substituer portent des noms explicites et sont identiques dans les deux langues,
pour qu'un test puisse vérifier qu'aucune traduction n'en oublie ni n'en invente.

La langue est un état global du processus, fixé une fois par :func:`definir_langue`
au démarrage. C'est volontaire : l'aide d'argparse est construite à l'import des
sous-parseurs, donc bien avant qu'on puisse consulter la ligne de commande
analysée — il faut donc connaître la langue avant de bâtir le parseur.
"""

from __future__ import annotations

import os
import re
import sys

LANGUES = ("fr", "en")

# Repli quand la locale est inconnue : l'anglais touche plus de monde.
LANGUE_PAR_DEFAUT = "en"

LANGUE_ENV = "HACHURE_LANG"

# Variables consultées dans cet ordre, comme le veut l'usage POSIX.
_ENV_LOCALE = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")

# Identifiant de langue principale de Windows (les 10 bits bas du LANGID).
_LANGID_PRINCIPAL = {0x09: "en", 0x0C: "fr"}

# Détectée dès l'import : le paquet se comporte pareil qu'il soit appelé par la
# CLI ou importé dans un script. main() la redéfinit si --lang est passé.
_langue_courante = LANGUE_PAR_DEFAUT


def normaliser(brut: str | None) -> str | None:
    """Ramène « fr_FR.UTF-8 », « French_France » ou « FR » à « fr »."""
    if not brut:
        return None
    code = re.split(r"[._@-]", brut.strip())[0].lower()
    if code in LANGUES:
        return code
    # Noms longs que Windows expose parfois dans LANG.
    return {"french": "fr", "francais": "fr", "français": "fr", "english": "en"}.get(code)


def _langue_de_windows() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError, ImportError):
        return None
    return _LANGID_PRINCIPAL.get(langid & 0x3FF)


def detecter_langue() -> str:
    """Déduit la langue de l'environnement, sans jamais échouer.

    ``locale.getdefaultlocale`` est dépréciée et la CI traite tout
    ``DeprecationWarning`` comme une erreur : on lit donc les variables
    d'environnement, puis on interroge Windows directement.
    """
    # HACHURE_LANG d'abord : un réglage propre au projet doit primer sur la
    # locale générale du système.
    for variable in (LANGUE_ENV, *_ENV_LOCALE):
        code = normaliser(os.environ.get(variable))
        if code:
            return code
    return _langue_de_windows() or LANGUE_PAR_DEFAUT


def definir_langue(code: str | None) -> str:
    """Fixe la langue courante. ``None`` ou une valeur inconnue déclenche la détection."""
    global _langue_courante
    _langue_courante = normaliser(code) or detecter_langue()
    return _langue_courante


def langue() -> str:
    return _langue_courante


def T(cle: str, **champs: object) -> str:
    """Rend le texte associé à ``cle`` dans la langue courante.

    Lève ``KeyError`` sur une clé absente plutôt que de renvoyer un texte de
    remplacement : une clé manquante est un défaut, et un test parcourt les
    sources pour qu'aucune n'échappe à la relecture.
    """
    try:
        textes = CATALOGUE[cle]
    except KeyError:
        raise KeyError(f"clé de traduction inconnue : {cle!r}") from None
    texte = textes[LANGUES.index(_langue_courante)]
    return texte.format(**champs) if champs else texte


# --------------------------------------------------------------------------- #
# Catalogue — chaque valeur est le couple (français, anglais)
# --------------------------------------------------------------------------- #

CATALOGUE: dict[str, tuple[str, str]] = {
    # ---------------------------------------------------------------- validation
    "validation.positif": (
        "doit être strictement positif",
        "must be greater than zero",
    ),
    "validation.nul_ou_positif": (
        "doit être nul ou positif",
        "must be zero or greater",
    ),
    "validation.fini_positif": (
        "doit être un nombre fini strictement positif",
        "must be a finite number greater than zero",
    ),
    "validation.fini_nul_ou_positif": (
        "doit être un nombre fini nul ou positif",
        "must be a finite number of zero or more",
    ),
    "validation.entre_0_et_1": (
        "doit être compris entre 0 et 1",
        "must be between 0 and 1",
    ),
    "validation.entre_01_et_2": (
        "doit être compris entre 0.1 et 2.0",
        "must be between 0.1 and 2.0",
    ),
    "validation.entre_01_et_5": (
        "doit être compris entre 0.1 et 5.0",
        "must be between 0.1 and 5.0",
    ),
    "validation.decalage_audio": (
        "doit être compris entre -30 et 30 secondes",
        "must be between -30 and 30 seconds",
    ),
    "validation.langue": (
        "doit être « fr », « en » ou « auto »",
        "must be 'fr', 'en' or 'auto'",
    ),

    # --------------------------------------------------------------------- aide
    "aide.programme": (
        "Rend images, vidéos, caméras et art 3D procédural dans un terminal.",
        "Render images, videos, cameras and procedural 3D art in a terminal.",
    ),
    "aide.aide": (
        "affiche ce message d'aide et quitte",
        "show this help message and exit",
    ),
    "aide.version": (
        "affiche la version du programme et quitte",
        "show the program's version number and exit",
    ),
    "aide.langue": (
        "langue de l'interface : fr, en, ou auto pour suivre le système "
        "(défaut : %(default)s)",
        "interface language: fr, en, or auto to follow the system "
        "(default: %(default)s)",
    ),
    "aide.charset": (
        "rampe luminosité-vers-caractère (défaut : %(default)s)",
        "brightness-to-character ramp (default: %(default)s)",
    ),
    "aide.invert": (
        "inverse les caractères sombres et clairs",
        "reverse dark and bright characters",
    ),
    "aide.cells": (
        "un pixel par cellule, ou deux pixels empilés par cellule (défaut : %(default)s)",
        "one pixel per cell, or two stacked pixels per cell (default: %(default)s)",
    ),
    "aide.half": (
        "raccourci de --cells half ; double la résolution verticale",
        "shorthand for --cells half; doubles the vertical resolution",
    ),
    "aide.color": (
        "active la sortie en couleur",
        "enable color output",
    ),
    "aide.no_color": (
        "force une sortie monochrome",
        "force monochrome output",
    ),
    "aide.color_depth": (
        "court-circuite la détection de couleur du terminal (défaut : %(default)s)",
        "override terminal color detection (default: %(default)s)",
    ),
    "aide.quant": (
        "pas de quantification des couleurs, pour réduire la sortie ANSI "
        "(défaut : %(default)s)",
        "color quantization step used to reduce ANSI output (default: %(default)s)",
    ),
    "aide.edges": (
        "remplace le caractère de rampe par un glyphe de ligne là où un contour "
        "traverse la cellule, ce qui rend les formes lisibles",
        "replace the ramp character with a line glyph where an edge runs through "
        "the cell, which makes shapes readable",
    ),
    "aide.edge_strength": (
        "force minimale d'un contour pour afficher un glyphe, de 0 à 1 "
        "(défaut : %(default)s)",
        "how strong an edge must be to show a glyph, 0 to 1 (default: %(default)s)",
    ),
    "aide.auto_levels": (
        "étire chaque image sur toute la rampe, au lieu de la seule plage que la "
        "source utilise",
        "stretch each frame onto the full ramp instead of the range the source "
        "happens to use",
    ),
    "aide.gamma": (
        "mise en forme des tons moyens ; au-dessus de 1 ça éclaircit "
        "(défaut : %(default)s)",
        "midtone shaping; above 1 brightens (default: %(default)s)",
    ),
    "aide.width_max": (
        "largeur maximale en caractères (défaut : %(default)s)",
        "maximum character width (default: %(default)s)",
    ),
    "aide.height_max": (
        "hauteur maximale en caractères",
        "maximum character height",
    ),
    "aide.fit": (
        "encadre la source de bandes, ou la recadre pour remplir le terminal "
        "(défaut : %(default)s)",
        "letterbox the source, or crop it to fill the terminal (default: %(default)s)",
    ),
    "aide.char_aspect": (
        "largeur d'une cellule divisée par sa hauteur, pour votre police "
        "(défaut : 0.5)",
        "cell width divided by cell height for your font (default: 0.5)",
    ),
    "aide.record": (
        "écrit ce qui est rendu dans un fichier .mp4 ou .gif",
        "write what is rendered to an .mp4 or .gif file",
    ),
    "aide.font_record": (
        ".ttf à chasse fixe utilisé à l'enregistrement",
        "monospace .ttf used when recording",
    ),
    "aide.font_size": (
        "taille de police utilisée à l'enregistrement (défaut : %(default)s)",
        "font size used when recording (default: %(default)s)",
    ),
    "aide.fps": (
        "cadence de lecture visée (défaut : %(default)s)",
        "target playback rate (default: %(default)s)",
    ),
    "aide.smoothing": (
        "lissage temporel : 1 est net, les valeurs plus basses ajoutent des traînées",
        "temporal smoothing: 1 is crisp, lower values add trails",
    ),
    "aide.max_frame_skip": (
        "nombre maximal d'images consécutives abandonnées pour rattraper le retard "
        "(défaut : %(default)s)",
        "maximum consecutive frames dropped to catch up (default: %(default)s)",
    ),
    "aide.cmd_menu": (
        "ouvre le menu interactif (comportement par défaut)",
        "open the interactive menu (the default behaviour)",
    ),
    "aide.cmd_list": (
        "liste les moteurs de rendu disponibles",
        "list available renderers",
    ),
    "aide.cmd_doctor": (
        "vérifie les dépendances et les capacités du terminal",
        "check dependencies and terminal capabilities",
    ),
    "aide.cmd_calibrate": (
        "construit une rampe de caractères mesurée sur une police",
        "build a character ramp measured from a font",
    ),
    "aide.font_mesurer": (
        ".ttf à chasse fixe à mesurer",
        "monospace .ttf to measure",
    ),
    "aide.length": (
        "nombre de caractères que la rampe doit contenir (défaut : %(default)s)",
        "how many characters the ramp should hold (default: %(default)s)",
    ),
    "aide.size_mesure": (
        "taille en pixels à laquelle les glyphes sont mesurés (défaut : %(default)s)",
        "pixel size the glyphs are measured at (default: %(default)s)",
    ),
    "aide.cmd_image": (
        "convertit une image fixe en ASCII",
        "convert a still image to ASCII",
    ),
    "aide.chemin_image": (
        "chemin vers une image",
        "path to an image",
    ),
    "aide.output": (
        "écrit le texte dans un fichier UTF-8",
        "write text to a UTF-8 file",
    ),
    "aide.cmd_video": (
        "lit une vidéo en ASCII",
        "play a video as ASCII",
    ),
    "aide.chemin_video": (
        "chemin vers une vidéo",
        "path to a video",
    ),
    "aide.loop": (
        "redémarre quand la vidéo se termine",
        "restart when the video ends",
    ),
    "aide.start": (
        "position de départ en secondes (défaut : %(default)s)",
        "start position in seconds (default: %(default)s)",
    ),
    "aide.duration": (
        "arrête après ce nombre de secondes",
        "stop after this many seconds",
    ),
    "aide.no_audio": (
        "désactive l'audio via FFplay",
        "disable FFplay audio",
    ),
    "aide.audio_delay": (
        "décalage audio en secondes ; une valeur positive retarde l'audio",
        "audio offset in seconds; positive values delay audio",
    ),
    "aide.cmd_camera": (
        "lit une caméra en direct en ASCII",
        "play a live camera as ASCII",
    ),
    "aide.device": (
        "nom ou chemin de la caméra",
        "camera name or path",
    ),
    "aide.list_cameras": (
        "liste les caméras disponibles et quitte",
        "list available cameras and exit",
    ),
    "aide.size_capture": (
        "taille de capture demandée, par exemple 1280x720",
        "requested capture size, for example 1280x720",
    ),
    "aide.cmd_demo": (
        "lance un moteur de rendu procédural",
        "run a procedural renderer",
    ),
    "aide.nom_demo": (
        "nom de la démo",
        "demo name",
    ),
    "aide.width": (
        "largeur en caractères",
        "character width",
    ),
    "aide.height": (
        "hauteur en caractères",
        "character height",
    ),

    # Libellés que produit argparse lui-même.
    "argparse.utilisation": (
        "utilisation : ",
        "usage: ",
    ),
    "argparse.positionnels": (
        "arguments positionnels",
        "positional arguments",
    ),
    "argparse.options": (
        "options",
        "options",
    ),

    # ------------------------------------------------------------------- démos
    "demo.cube": (
        "Cube plein en rotation, avec éclairage et tampon de profondeur",
        "Rotating filled cube, with lighting and depth buffering",
    ),
    "demo.sphere": (
        "Sphère en rotation, ombrée mathématiquement",
        "Mathematically shaded rotating sphere",
    ),
    "demo.donut": (
        "Tore paramétrique, avec éclairage et tampon de profondeur",
        "Parametric torus, with lighting and depth buffering",
    ),
    "demo.planet": (
        "Planète procédurale, avec relief et halo atmosphérique",
        "Procedural planet, with terrain and an atmospheric rim",
    ),
    "demo.blackhole": (
        "Disque d'accrétion stylisé, étoiles et anneau de photons",
        "Stylized accretion disk, stars and photon ring",
    ),
    "erreur.demo_inconnue": (
        "Démo inconnue : {nom}",
        "Unknown demo: {nom}",
    ),

    # -------------------------------------------------------------------- list
    "liste.entrees": (
        "Moteurs de rendu d'entrée :",
        "Input renderers:",
    ),
    "liste.image": (
        "Images fixes, via Pillow",
        "Still images, through Pillow",
    ),
    "liste.video": (
        "Fichiers vidéo, via FFmpeg",
        "Video files, through FFmpeg",
    ),
    "liste.camera": (
        "Capture caméra en direct, via FFmpeg",
        "Live camera capture, through FFmpeg",
    ),
    "liste.demos": (
        "Démos procédurales :",
        "Procedural demos:",
    ),

    # ------------------------------------------------------------------ doctor
    "doctor.terminal": ("terminal", "terminal"),
    "doctor.cellules": ("cellules", "cells"),
    "doctor.profondeur": ("profondeur", "color depth"),
    "doctor.rapport": ("rapport cell.", "char aspect"),
    "doctor.tty": ("tty stdout", "stdout tty"),
    "doctor.codec": ("codec stdout", "stdout codec"),
    "doctor.absent": ("ABSENT", "MISSING"),
    "doctor.inconnu": ("inconnue", "unknown"),
    "doctor.hors_path": ("absent du PATH", "not found on PATH"),
    "doctor.video_manquante": (
        "\nLa lecture vidéo a besoin de {outils}. Installez FFmpeg puis rouvrez "
        "votre terminal.",
        "\nVideo playback needs {outils}. Install FFmpeg and reopen your terminal.",
    ),

    # --------------------------------------------------------------- calibrate
    "calibrate.police": ("Police", "Font"),
    "calibrate.rampe": ("Rampe", "Ramp"),
    "calibrate.conseil": (
        "\nAjoutez-la à CHARSETS dans charsets.py pour l'utiliser avec --charset, "
        "ou comparez-la aux rampes intégrées :",
        "\nAdd it to CHARSETS in charsets.py to use it with --charset, or compare "
        "it against the built-in ramps:",
    ),
    "erreur.police_absente": (
        "Aucune police à chasse fixe n'a été trouvée. Passez --font avec un chemin "
        "vers un .ttf.",
        "No monospace font was found. Pass --font with a path to a .ttf.",
    ),
    "erreur.police_introuvable": (
        "Police introuvable : {chemin}",
        "Font not found: {chemin}",
    ),

    # ------------------------------------------------------------------- image
    "image.ecrite": (
        "Image ASCII {colonnes} x {lignes} écrite dans {chemin}",
        "Wrote {colonnes} x {lignes} ASCII image to {chemin}",
    ),
    "erreur.image_introuvable": (
        "Image introuvable : {chemin}",
        "Image not found: {chemin}",
    ),
    "erreur.image_pillow": (
        "Le rendu d'image exige Pillow. Installez d'abord les dépendances du projet.",
        "Image rendering requires Pillow. Install the project dependencies first.",
    ),
    "erreur.image_numpy": (
        "Le rendu d'image exige NumPy. Installez d'abord les dépendances du projet.",
        "Image rendering requires NumPy. Install the project dependencies first.",
    ),
    "erreur.image_ouverture": (
        "Impossible d'ouvrir l'image '{chemin}' : {cause}",
        "Could not open image '{chemin}': {cause}",
    ),
    "erreur.image_rendu": (
        "Impossible de rendre l'image '{chemin}' : {cause}",
        "Could not render image '{chemin}': {cause}",
    ),
    "erreur.image_canaux": (
        "Impossible de lire les canaux de couleur de '{chemin}'.",
        "Could not read color channels from '{chemin}'.",
    ),

    # ------------------------------------------------------------------- vidéo
    "lecture.source": ("Source", "Source"),
    "lecture.rendu": ("Rendu", "Render"),
    "lecture.cellules": ("Cellules", "Cells"),
    "lecture.couleur": ("Couleur", "Color"),
    "lecture.ajustement": ("Ajustement", "Fit"),
    "lecture.audio": ("Audio", "Audio"),
    "lecture.active": ("activé", "enabled"),
    "lecture.desactive": ("désactivé", "disabled"),
    "lecture.ips": ("IPS", "FPS"),
    "lecture.pixels": ("pixels", "pixels"),
    "lecture.demarrage": (
        "Démarrage... Appuyez sur Ctrl+C pour arrêter.",
        "Starting... Press Ctrl+C to stop.",
    ),
    "lecture.interrompue": ("Lecture interrompue.", "Playback stopped."),
    "lecture.terminee": ("Lecture terminée.", "Playback finished."),
    "erreur.video_introuvable": (
        "Vidéo introuvable : {chemin}",
        "Video not found: {chemin}",
    ),
    "erreur.video_numpy": (
        "Le rendu vidéo exige NumPy. Installez d'abord les dépendances du projet.",
        "Video rendering requires NumPy. Install the project dependencies first.",
    ),
    "erreur.ffmpeg_absent": (
        "FFmpeg est introuvable dans le PATH.",
        "FFmpeg was not found on PATH.",
    ),
    "erreur.ffplay_absent": (
        "FFplay est introuvable dans le PATH. Utilisez --no-audio pour continuer.",
        "FFplay was not found on PATH. Use --no-audio to continue.",
    ),
    "erreur.duree_positive": (
        "La durée doit être strictement positive.",
        "Duration must be greater than zero.",
    ),
    "erreur.flux_absent": (
        "FFmpeg n'a pas fourni de flux vidéo.",
        "FFmpeg did not provide a video stream.",
    ),
    "erreur.decodage": (
        "FFmpeg n'a pas pu décoder la source.",
        "FFmpeg could not decode the source.",
    ),
    "erreur.lecture_demarrage": (
        "Impossible de démarrer la lecture du média : {cause}",
        "Could not start media playback: {cause}",
    ),
    "erreur.processus_media": (
        "Le processus média a échoué : {cause}",
        "Media process failed: {cause}",
    ),
    "erreur.camera_absente": (
        "Aucune caméra DirectShow n'a été trouvée. Lancez « hachure camera --list » "
        "pour voir les périphériques disponibles.",
        "No DirectShow camera was found. Run 'hachure camera --list' to see "
        "available devices.",
    ),
    "erreur.camera_acces": (
        "La caméra est bien listée mais n'a pas pu être ouverte. Sous Windows, "
        "autorisez les applications de bureau dans Paramètres > Confidentialité et "
        "sécurité > Caméra, et fermez toute autre application qui l'utilise déjà.",
        "The camera was listed but could not be opened. On Windows, allow desktop "
        "apps under Settings > Privacy & security > Camera, and close any other "
        "application already using it.",
    ),

    # ------------------------------------------------------------------ caméra
    "camera.titre": ("Caméras :", "Cameras:"),
    "camera.aucune": (
        "Aucune caméra signalée. Sous Linux et macOS, passez --device.",
        "No cameras were reported. On Linux and macOS, pass --device.",
    ),

    # ----------------------------------------------------------- enregistrement
    "enreg.images": (
        "{nombre} images enregistrées dans {chemin}",
        "Recorded {nombre} frames to {chemin}",
    ),
    "erreur.enreg_pillow": (
        "L'enregistrement exige Pillow.",
        "Recording requires Pillow.",
    ),
    "erreur.enreg_ffmpeg": (
        "L'enregistrement exige FFmpeg dans le PATH.",
        "Recording requires FFmpeg on PATH.",
    ),
    "erreur.enreg_police": (
        "Aucune police à chasse fixe n'a été trouvée pour l'enregistrement. "
        "Installez DejaVu Sans Mono ou passez --font avec un chemin vers un .ttf.",
        "No monospace font was found for recording. Install DejaVu Sans Mono or "
        "pass --font with a .ttf path.",
    ),
    "erreur.police_chargement": (
        "Impossible de charger la police '{chemin}' : {cause}",
        "Could not load font '{chemin}': {cause}",
    ),
    "erreur.enreg_interrompu": (
        "L'enregistrement s'est interrompu de façon inattendue : {cause}",
        "Recording stopped unexpectedly: {cause}",
    ),
    "erreur.enreg_ecriture": (
        "FFmpeg n'a pas pu écrire l'enregistrement.",
        "FFmpeg could not write the recording.",
    ),

    # ------------------------------------------------------------- rampes, ton
    "erreur.rampe_vide": (
        "Une rampe de caractères ne peut pas être vide.",
        "A character ramp cannot be empty.",
    ),
    "erreur.rampe_deux": (
        "Une rampe demande au moins deux caractères.",
        "A ramp needs at least two characters.",
    ),
    "erreur.mesures_absentes": (
        "Aucune mesure de glyphe n'a été fournie.",
        "No glyph measurements were supplied.",
    ),
    "erreur.couverture_plate": (
        "La couverture des glyphes n'a pas varié ; la police est-elle à chasse fixe ?",
        "Glyph coverage did not vary; is the font monospaced?",
    ),
    "erreur.charset_inconnu": (
        "Jeu de caractères '{nom}' inconnu. Choix possibles : {choix}.",
        "Unknown charset '{nom}'. Choose from: {choix}.",
    ),
    "erreur.percentiles": (
        "Les percentiles doivent vérifier 0 <= bas < haut <= 100.",
        "Percentiles must satisfy 0 <= low < high <= 100.",
    ),
    "erreur.inertie": (
        "L'inertie des niveaux doit être comprise entre 0 et 1.",
        "Level inertia must be between 0 and 1.",
    ),
    "erreur.rvb_requis": (
        "Le rendu en couleur exige un tableau RVB.",
        "Color rendering needs an RGB array.",
    ),

    # --------------------------------------------------------------- géométrie
    "erreur.source_positive": (
        "Les dimensions de la source doivent être positives.",
        "Source dimensions must be positive.",
    ),
    "erreur.grille_positive": (
        "Les dimensions de la grille doivent être positives.",
        "Grid dimensions must be positive.",
    ),
    "erreur.rapport_positif": (
        "La correction de rapport des caractères doit être positive.",
        "Character aspect correction must be positive.",
    ),
    "erreur.hauteur_positive": (
        "Le rapport de hauteur doit être positif.",
        "Height ratio must be positive.",
    ),
    "erreur.fps_positif": (
        "Le nombre d'images par seconde doit être positif.",
        "FPS must be positive.",
    ),

    # ---------------------------------------------------------------- générale
    "erreur.prefixe": ("erreur : ", "error: "),
    "arret.demo": ("{nom} arrêté.", "{nom} stopped."),

    # -------------------------------------------------------------------- menu
    "menu.banniere": (
        "hachure · rendu d'images, de vidéos et de 3D en caractères",
        "hachure · images, video and 3D rendered as characters",
    ),
    "menu.touches": (
        "↑↓ déplacer · Entrée valider · Échap revenir",
        "↑↓ move · Enter select · Esc back",
    ),
    "menu.touches_reglages": (
        "↑↓ déplacer · Espace/←→ changer · Entrée ouvrir · Échap revenir",
        "↑↓ move · Space/←→ change · Enter open · Esc back",
    ),
    "menu.au_dessus": ("↑ {nombre} au-dessus", "↑ {nombre} above"),
    "menu.en_dessous": ("↓ {nombre} en dessous", "↓ {nombre} below"),
    "menu.choix": (
        "Choix (vide pour revenir) :",
        "Choice (empty to go back):",
    ),
    "menu.choix_invalide": (
        "Entrez un nombre entre 1 et {nombre}.",
        "Enter a number between 1 and {nombre}.",
    ),
    "menu.defaut": ("défaut", "default"),
    # Unités de taille de fichier, du plus petit au plus grand.
    "taille.octet": ("o", "B"),
    "taille.kilo": ("Ko", "KB"),
    "taille.mega": ("Mo", "MB"),
    "taille.giga": ("Go", "GB"),
    "menu.oui": ("oui", "yes"),
    "menu.non": ("non", "no"),
    "menu.aucun": ("aucun", "none"),
    "menu.quitter": ("Quitter", "Quit"),
    "menu.annuler": ("[ annuler ]", "[ cancel ]"),
    "menu.lancer": ("Lancer le rendu", "Start rendering"),
    "menu.mesurer": ("Lancer la mesure", "Start measuring"),
    "menu.annuler_ligne": ("Annuler", "Cancel"),
    "menu.reglages": ("Réglages", "Settings"),
    "menu.garder_valeur": (
        "Entrée pour garder la valeur affichée",
        "Enter keeps the value shown",
    ),
    "menu.vide_pour_revenir": (
        "vide pour revenir",
        "empty to go back",
    ),
    "menu.vide_pour_aucun": (
        "vide pour aucun",
        "empty for none",
    ),
    "menu.fichier_introuvable": (
        "Fichier introuvable : {chemin}",
        "File not found: {chemin}",
    ),
    "menu.cameras_indisponibles": (
        "Liste des caméras indisponible : {cause}",
        "Camera list unavailable: {cause}",
    ),

    # Entrées du menu principal
    "menu.image": ("Image fixe", "Still image"),
    "menu.image_detail": (
        "convertir une photo en caractères",
        "turn a photo into characters",
    ),
    "menu.video": ("Vidéo", "Video"),
    "menu.video_detail": ("lire un fichier vidéo", "play a video file"),
    "menu.camera": ("Caméra", "Camera"),
    "menu.camera_detail": (
        "diffuser une caméra en direct",
        "stream a live camera",
    ),
    "menu.demo": ("Démo procédurale", "Procedural demo"),
    "menu.demo_detail": (
        "cube, sphère, tore, planète, trou noir",
        "cube, sphere, torus, planet, black hole",
    ),
    "menu.doctor": ("Diagnostic", "Diagnostics"),
    "menu.doctor_detail": (
        "dépendances et capacités du terminal",
        "dependencies and terminal capabilities",
    ),
    "menu.moteurs": ("Moteurs disponibles", "Available renderers"),
    "menu.moteurs_detail": (
        "ce que le projet sait rendre",
        "what the project can render",
    ),
    "menu.calibrer": ("Calibrer une rampe", "Calibrate a ramp"),
    "menu.calibrer_detail": (
        "mesurer une police à chasse fixe",
        "measure a monospace font",
    ),

    # Invites de choix de source
    "menu.quelle_image": ("Quelle image ?", "Which image?"),
    "menu.quelle_video": ("Quelle vidéo ?", "Which video?"),
    "menu.quelle_camera": ("Quelle caméra ?", "Which camera?"),
    "menu.quelle_demo": ("Quelle démo ?", "Which demo?"),
    "menu.camera_defaut": ("Caméra par défaut", "Default camera"),

    # Navigateur de fichiers
    "menu.dossier_parent": ("dossier parent", "parent folder"),
    "menu.dossier": ("dossier", "folder"),
    "menu.choisir_dossier": (
        "[ choisir ce dossier ]",
        "[ choose this folder ]",
    ),
    "menu.changer_disque": (
        "[ changer de disque ]",
        "[ change drive ]",
    ),
    "menu.quel_disque": ("Quel disque ?", "Which drive?"),
    "menu.rien_ici": (
        "( rien à afficher ici )",
        "( nothing to show here )",
    ),
    "menu.liste_limitee": (
        "( liste limitée à {nombre} entrées )",
        "( list capped at {nombre} entries )",
    ),
    "menu.ou_enregistrer": (
        "{libelle} — où enregistrer ?",
        "{libelle} — where to save?",
    ),
    "menu.nom_fichier": ("Nom du fichier", "File name"),

    # Libellés des champs de réglage
    "champ.color": ("Couleur", "Color"),
    "champ.edges": ("Contours (--edges)", "Edges (--edges)"),
    "champ.auto_levels": ("Niveaux automatiques", "Auto levels"),
    "champ.charset": ("Jeu de caractères", "Character ramp"),
    "champ.cells": ("Géométrie de cellule", "Cell geometry"),
    "champ.invert": ("Inverser la rampe", "Invert the ramp"),
    "champ.width_max": ("Largeur maximale", "Maximum width"),
    "champ.height_max": ("Hauteur maximale", "Maximum height"),
    "champ.fit": ("Ajustement", "Fit"),
    "champ.width": ("Largeur", "Width"),
    "champ.height": ("Hauteur", "Height"),
    "champ.fps": ("Images par seconde", "Frames per second"),
    "champ.no_audio": ("Couper le son", "Mute the sound"),
    "champ.loop": ("Lire en boucle", "Loop playback"),
    "champ.start": ("Départ en secondes", "Start, in seconds"),
    "champ.duration": ("Durée en secondes", "Duration, in seconds"),
    "champ.output": (
        "Écrire dans un fichier texte",
        "Write to a text file",
    ),
    "champ.record": ("Enregistrer le rendu", "Record the render"),
    "champ.font": ("Police à mesurer", "Font to measure"),
    "champ.length": ("Longueur de la rampe", "Ramp length"),
    "champ.size": (
        "Taille de mesure en pixels",
        "Measurement size, in pixels",
    ),
}


# Le catalogue devait être défini avant tout appel : on détecte maintenant.
_langue_courante = detecter_langue()
