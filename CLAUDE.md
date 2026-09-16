# CLAUDE.md

Ce fichier guide Claude Code (claude.ai/code) lorsqu'il travaille sur ce dépôt.

## Projet

`hachure` — une CLI Python qui rend images, vidéos, caméras en direct et scènes 3D procédurales
sous forme de texte ASCII/ANSI dans un terminal. Le point d'entrée unique est le script console
`hachure` (`hachure.cli:main`). **Appelé sans argument, `hachure` ouvre un menu interactif** ; les
sous-commandes restent utilisables directement.

Le projet s'appelait auparavant `terminal-ascii-art` (module `terminal_ascii_art`, commande
`ascii-art`). **`hachure` n'est pas encore sur PyPI** — `terminal-ascii-art` l'est, publié par les
auteurs amont crédités dans `pyproject.toml`. `publish.yml` cible `pypi.org/p/hachure` : la première
release réclamera donc un nom neuf au lieu de mettre à jour le paquet existant. `project.urls`
pointe vers `github.com/Josueagbeta0/hachure-ascii`.

Le projet dérive d'un travail MIT de Niladri Pal et Talal Alqahs : **`LICENSE` conserve leur notice
de copyright**, comme la licence l'exige, alors que `pyproject.toml` ne liste que le mainteneur
actuel. Ne pas « corriger » cet écart, il est voulu ; le README l'explique dans ses crédits.

## Langue

**Tout le contenu rédigé du dépôt est en français** : docstrings, commentaires, textes d'aide
argparse, sorties console, messages d'erreur, README et `docs/`. Les noms de classes et de méthodes
de test sont également en français, en ASCII sans accents
(`test_une_forte_arete_verticale_devient_un_glyphe_de_bloc`) ; les accents ne servent que dans les
chaînes, commentaires et docstrings. Toute contribution suit cette règle.

Deux exceptions délibérées, marquées par un commentaire à leur emplacement :

- Les sous-chaînes comparées à la sortie de FFmpeg (`"I/O error"`,
  `"Could not find video device"` dans `media/video.py`) restent en anglais, puisqu'elles décrivent
  ce que FFmpeg écrit.
- Les messages internes d'argparse (`invalid choice`, `the following arguments are required`,
  `unrecognized arguments`) et ceux d'`unittest` restent en anglais : ils passent par gettext et
  CPython ne livre aucun catalogue français. Ce qui *est* francisé dans l'aide — préfixe
  `utilisation :`, titres de sections, texte de `-h` — l'est via `_FrenchHelpFormatter` et
  `_localize` dans `cli.py`, qui touchent `parser._positionals.title` / `_optionals.title`.

## Commandes

```powershell
python -m pip install -e ".[dev]"          # installation dev (ajoute pytest)

python -m unittest discover -s tests -v    # suite complète, exactement comme la CI
python -m pytest                           # équivalent ; tests en unittest, compatibles pytest
python -m pytest tests/test_render.py -k half        # un fichier / un motif
python -m unittest tests.test_render.RenduMonochromeTests   # une classe
python -W error::DeprecationWarning -m unittest discover -s tests   # forme stricte de la CI

hachure               # menu interactif (équivalent : hachure menu)
hachure doctor        # dépendances, outils FFmpeg, taille du terminal, profondeur de couleur —
                      # le premier réflexe pour déboguer un rendu
hachure list
```

Ni linter ni formateur configuré. La CI (`.github/workflows/ci.yml`) lance la suite sur Python 3.10
et 3.14, plus `hachure --version` / `hachure list`.

Releases : `publish.yml` se déclenche sur une release GitHub publiée et **vérifie que `__version__`
dans `hachure/__init__.py` égale le tag privé de son préfixe `v`** — incrémentez cette constante
dans le commit même du tag de release.

FFmpeg, FFplay et FFprobe doivent être dans le `PATH` pour les commandes `video` et `camera` ; c'est
une dépendance système externe, pas une dépendance Python.

## Docs

`docs/INSTALLATION.md` et `docs/installation.html` portent le même guide d'installation sous deux
formats — la version HTML est une page autonome destinée à être ouverte depuis le disque, d'où son
propre `<!doctype>`/`<head>` et ses styles en ligne. Leur contenu est dupliqué : **une modification
de l'un doit être répercutée sur l'autre**. Les deux citent de vraies sorties capturées (`doctor`,
l'exécution des tests, `camera --list`), qui périment dès que le format de sortie de la CLI change.

## Architecture

Tout converge vers un unique point de conversion. Deux familles de sources (pixels décodés,
géométrie procédurale) et trois destinations (terminal, fichier texte, vidéo enregistrée) se
rejoignent dans `render.py`.

```
image.py (Pillow) ─┐
video.py (FFmpeg) ─┼→ tableau NumPy ─→ tone.py ─→ edges.py ─→ render.py ─→ texte ANSI ─┬→ terminal.py Screen
renderers/*.py ────┘   (les rendus procéduraux émettent du texte directement)  color.py └→ export.py (mp4/gif)
```

- **`render.py`** est le pivot. `RenderStyle` est une dataclass gelée portant la rampe, le mode de
  cellule, la profondeur de couleur, la quantification et les réglages de contour ; ses
  `pixel_cols()`/`pixel_rows()` indiquent au décodeur *en amont* combien de pixels source réclame une
  grille de caractères. Deux géométries de cellule : `char` (un pixel par cellule, la luminosité
  choisit un glyphe de la rampe) et `half` (deux pixels empilés dessinés avec `▀`, premier plan =
  haut, arrière-plan = bas). La sortie est construite en plages compressées par ligne via `_row_runs`,
  jamais cellule par cellule — les plages ne franchissent volontairement jamais une frontière de
  ligne, pour que chaque ligne reste redessinable indépendamment.
- **`edges.py`** suréchantillonne la source 3× par côté de cellule et utilise un *tenseur de
  structure* (et non un gradient moyenné, qui s'annule sur les lignes fines) pour choisir l'un de
  `- \ | /`. Les glyphes de contour sont ajoutés après la fin de la rampe dans
  `RenderStyle.alphabet`, si bien que le code en aval indexe un alphabet unique sans cas particulier.
- **`tone.py`** `ToneMapper` applique des niveaux automatiques (2e/98e percentile, lissés d'une image
  à l'autre par inertie pour que la lecture ne pulse pas) et le gamma. Il est à état entre les
  images — appelez `reset()` sur un saut ou un redémarrage de boucle.
- **`color.py`** `AnsiPalette` mémoïse les préfixes d'échappement, indexés par RVB compacté ; la
  détection de profondeur lit `NO_COLOR`, `COLORTERM`, `TERM` et des indices propres à Windows.
- **`terminal.py`** gère le dimensionnement et la boucle d'animation. `Screen.draw()` compare à
  l'image précédente et ne repeint que les lignes modifiées. `fit_source_size` / `source_crop`
  implémentent `contain` contre `cover` ; `char_aspect` (défaut 0.5, surchargeable par
  `HACHURE_CHAR_ASPECT`) corrige les cellules non carrées. `terminal_session()` garantit la
  restauration du curseur et des couleurs, et prend en charge l'activation du mode VT sous Windows
  ainsi que la sortie UTF-8.
- **`media/video.py`** construit une commande FFmpeg (filtres fps/crop/scale, rawvideo `rgb24` ou
  `gray` sur stdout), lit des images brutes de taille fixe et suit un calendrier à l'horloge murale,
  en abandonnant un nombre borné d'images décodées (`--max-frame-skip`) plutôt que de laisser la
  dérive croître. L'audio est un processus FFplay distinct. Les métadonnées de rotation issues
  d'`ffprobe` sont respectées au calcul des dimensions.
- **`renderers/`** sont des démos procédurales autonomes, enregistrées dans un dictionnaire `DEMOS`
  de dataclasses `Demo` ; chaque `render_frame(index, cols, rows, ramp) -> str` renvoie du texte fini
  et contourne entièrement `render.py`. Ajouter une démo = un nouveau module plus une entrée
  `Demo(...)`.
- **`export.py`** `FrameRecorder` réanalyse les codes d'échappement ANSI qu'on lui passe et les
  repeint avec une police à chasse fixe, en redirigeant vers FFmpeg. Il est branché comme
  `FrameSink`/`on_frame`, donc l'enregistrement capture exactement ce que le terminal a montré.
- **`menu.py`** porte le menu interactif. Il ne duplique aucune option : chaque écran **compose une
  liste d'arguments** puis la passe à `main()`, si bien qu'argparse reste seul juge des drapeaux et
  de leurs défauts. **Sur un terminal, rien ne se tape** — c'est la contrainte de conception du
  module, et toute extension doit la respecter.
  - Les champs de réglage sont des dataclasses (`Bascule`, `Choix`, `Fichier`, `Sortie`) exposant
    toutes `affichage()`, `modifier()`, `ouvrir()` et `argv()`. `Choix` traite une valeur vide comme
    « garder le défaut de la CLI » et n'émet alors rien : c'est ce qui évite de recopier les défauts
    d'argparse. Il n'existe pas de champ de saisie libre ; une valeur numérique est un `Choix` sur
    une liste de réglages courants (`_LARGEURS`, `_FPS`, `_DUREES`, …).
  - Les jeux de champs par commande (`champs_image`, `champs_video`, …) sont des données, pas du code
    d'affichage. Ils prennent une `base` qui sert à nommer les enregistrements proposés.
  - `parcourir()` est le navigateur de fichiers : il filtre sur `EXTENSIONS_IMAGE` / `_VIDEO` /
    `_POLICE`, montre toujours les dossiers, mémorise le dernier visité, et gère les racines de
    disque sous Windows. `choisir_destination()` s'en sert pour désigner un dossier, puis propose des
    noms fabriqués (`noms_proposes`), horodatés en variante — un fichier à écrire ne peut pas être
    pointé dans une arborescence.
  - `_dessiner_liste()` est la primitive d'affichage commune : elle raccourcit chaque ligne à la
    largeur du terminal (`_raccourcir`, élision au milieu) et n'affiche qu'une **fenêtre défilante**
    (`_debut_fenetre`). Les deux sont nécessaires, pas cosmétiques : une ligne repliée ou un bloc
    plus haut que l'écran fait défiler la console et désynchronise le repeint en place de `_Zone`,
    qui compte les lignes qu'il a écrites pour remonter le curseur.
  - Deux modes d'entrée : navigation aux flèches sur un vrai terminal, listes numérotées lues par
    `input()` dès que l'entrée ou la sortie est redirigée. `interactif()` arbitre. C'est le second
    mode que la plupart des tests exercent, ce qui évite d'ouvrir un terminal ; le premier est testé
    en simulant `lire_touche`.
  - `_lire_ligne()` retire le BOM UTF-8 que PowerShell préfixe à tout stdin redirigé. Sans lui, la
    première réponse arrivant par un pipe est systématiquement rejetée.
- **`cli.py`** n'utilise qu'argparse : `_add_style_options` / `_add_geometry_options` /
  `_add_playback_options` / `_add_record_options` sont partagés entre les sous-commandes, et
  `_build_style` / `_build_tone` / `_video_options` traduisent le namespace vers les dataclasses
  ci-dessus. Chaque sous-parseur, créé par `_subparser`, définit un `handler` ; `main()` attrape les
  types d'erreur des modules (`ImageRenderError`, `VideoRenderError`, `ExportError`) et sort avec 2.
  Les sous-commandes ne sont **pas** obligatoires : `args.command is None` route vers le menu.

## Conventions

- `from __future__ import annotations` en tête de chaque module ; annotations de type partout.
- NumPy et Pillow sont importés paresseusement dans des helpers `_load_numpy()` / `_load_pillow()`
  qui lèvent le type d'erreur propre au module. Les fonctions manipulant des tableaux prennent `np`
  en paramètre explicite plutôt que de l'importer au niveau du module — conservez ce style de
  signature en étendant `render.py`, `edges.py` ou `tone.py`.
- Les commentaires de ce dépôt expliquent *pourquoi* un choix non évident a été fait (tenseur de
  structure plutôt que gradients moyennés, plages bornées à la ligne, inertie des niveaux).
  Alignez-vous là-dessus ; ne paraphrasez pas ce que fait le code.
- Les tests sont des classes `unittest.TestCase` aux noms de méthodes longs et descriptifs, en
  français sans accents (`test_une_forte_arete_verticale_devient_un_glyphe_de_bloc`). Ils vérifient
  des chaînes rendues à partir de minuscules tableaux NumPy construits à la main, et simulent
  `subprocess` pour tout ce qui touche à FFmpeg — aucun vrai fichier média ni vrai terminal dans les
  tests.
- Les validateurs argparse (`_positive_int`, `_unit_float`, `_gamma`, …) vivent en tête de `cli.py` ;
  réutilisez-les au lieu de valider dans les handlers.
