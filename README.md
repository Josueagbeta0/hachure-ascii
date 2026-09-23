# hachure

Rendre des images, des vidéos, une caméra en direct et des scènes 3D procédurales **en caractères, dans un terminal**.

> **English** — `hachure` renders images, videos, live cameras and procedural 3D scenes as characters
> in your terminal. **The interface speaks English too**: it follows your system language, or you can
> force it with `hachure --lang en` or `HACHURE_LANG=en`. Run `hachure` with no arguments for a
> keyboard-driven menu, or `hachure --lang en --help` for the full option list. This README is in
> French; every command, message and help text below has an English counterpart built in.

La *hachure* est la technique qui rend le ton et la forme par des traits directionnels. C'est
littéralement ce que fait ce moteur : une rampe de luminosité pour le ton, et un tenseur de
structure qui choisit `-`, `\`, `|` ou `/` par cellule pour la forme.

Tape `hachure`, sans rien d'autre, et navigue au clavier. Aucun argument à retenir, aucun chemin à
taper : un menu, un navigateur de fichiers, des réglages qui se parcourent.

```text
pixels source ou géométrie 3D
              ↓
     luminosité / éclairage
              ↓
 niveaux automatiques et gamma
              ↓
orientation du contour par cellule
              ↓
 correspondance caractère ou bloc
              ↓
    couleur ANSI facultative
              ↓
           terminal
```

---

## Sommaire

[Le menu](#le-menu) · [Installation](#installation) · [Langue](#langue-de-linterface) ·
[En ligne de commande](#en-ligne-de-commande) ·
[Le mode caractère](#tirer-le-meilleur-du-mode-caractère) · [Image](#rendu-dimage) ·
[Vidéo](#rendu-vidéo) · [Caméra](#capture-caméra) · [Enregistrement](#enregistrement) ·
[Démos](#démos-procédurales) · [Couleurs](#couleurs) · [Performance](#notes-de-performance) ·
[Développement](#développement) · [Crédits](#crédits)

---

## Le menu

Une seule commande, sans argument :

```powershell
hachure
```

```text
hachure · rendu d'images, de vidéos et de 3D en caractères

  Image fixe           convertir une photo en caractères
› Vidéo                lire un fichier vidéo
  Caméra               diffuser une caméra en direct
  Démo procédurale     cube, sphère, tore, planète, trou noir
  Diagnostic           dépendances et capacités du terminal
  Moteurs disponibles  ce que le projet sait rendre
  Calibrer une rampe   mesurer une police à chasse fixe
  Quitter

↑↓ déplacer · Entrée valider · Échap revenir
```

**Rien ne se tape.** Choisis une source et un navigateur de fichiers s'ouvre, filtré sur les formats
que la commande sait lire, avec la taille de chaque fichier :

```text
Quelle vidéo ?
C:\Users\moi\Videos

› ..                     dossier parent
  archives/              dossier
  vacances/              dossier
  concert.mp4            84.2 Mo
  timelapse.mkv          12.7 Mo
  [ changer de disque ]
  [ annuler ]
```

Puis un écran de réglages, où chaque ligne se change sans jamais saisir de valeur — `Espace` ou
←→ pour passer à la suivante, `Entrée` pour ouvrir la liste complète :

```text
Réglages · video

  Largeur maximale     160
  Hauteur maximale     défaut
  Ajustement           cover
  Couleur              oui
› Contours (--edges)   oui
  Niveaux automatiques oui
  Jeu de caractères    detailed
  Géométrie de cellule char
  Inverser la rampe    non
  Images par seconde   24
  Couper le son        non
  Lire en boucle       non
  Départ en secondes   défaut
  Durée en secondes    30
  Enregistrer le rendu concert.mp4

  Lancer le rendu
  Annuler

hachure … --width 160 --fit cover --color --edges --auto-levels --charset detailed --fps 24 …
↑↓ déplacer · Espace/←→ changer · Entrée ouvrir · Échap revenir
```

La ligne du bas est le point important : **le menu ne fait que composer une ligne de commande**, il
te la montre, puis il la joue. Tu repars donc en sachant quoi retaper directement :

```text
$ hachure video concert.mp4 --width 160 --fit cover --color --edges --auto-levels --charset detailed
```

Un réglage laissé sur `défaut` n'est pas transmis : c'est la valeur par défaut de la CLI qui
s'applique, jamais une copie figée dans le menu.

`hachure menu` ouvre le même écran explicitement. Quand l'entrée ou la sortie est redirigée — un
pipe, un script, Git Bash, où Python ne reconnaît pas le terminal — la navigation aux flèches
devient impossible : le menu retombe alors sur des listes numérotées, et toutes les sous-commandes
ci-dessous restent utilisables directement.

---

## Installation

### Prérequis

| Composant | Rôle |
| --- | --- |
| **Python ≥ 3.10** | La CI valide 3.10 et 3.14. NumPy et Pillow s'installent automatiquement. |
| **ffmpeg** | Décode la vidéo et la caméra en images brutes. Requis par `video` et `camera` seulement. |
| **ffprobe** | Lit dimensions et rotation de la source, pour redresser une vidéo filmée verticalement. |
| **ffplay** | Lit la piste audio en parallèle. Facultatif : `--no-audio` s'en passe. |
| **Police à chasse fixe** | Doit contenir `▀` et `▄` pour le mode demi-bloc. Cascadia Mono, Consolas, DejaVu Sans Mono, Menlo. |
| **Terminal truecolor** | Windows Terminal, VS Code ou tout émulateur moderne, pour `--color` en 24 bits. |

FFmpeg livre les trois binaires ensemble. **Rouvre le terminal après l'installation**, pour que le
`PATH` soit rechargé :

```powershell
winget install Gyan.FFmpeg     # Windows
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Debian / Ubuntu
```

### Depuis les sources

```powershell
git clone https://github.com/Josueagbeta0/hachure-ascii.git
cd hachure-ascii
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

L'extra `dev` ajoute pytest. `-e` installe en mode éditable : le paquet pointe vers les sources, une
modification est prise en compte sans réinstaller.

### Pour que `hachure` réponde partout

Installé dans un environnement virtuel, `hachure` n'existe que quand cet environnement est activé.
Pour l'avoir dans n'importe quel terminal, installe-le dans ton Python principal, dont le dossier
`Scripts` est déjà dans le `PATH` :

```powershell
py -m pip install -e "C:\chemin\vers\hachure-ascii"
```

Si la commande reste introuvable, la forme module fonctionne toujours :

```powershell
python -m hachure
```

### Vérifier

```powershell
hachure doctor
```

```text
hachure       0.3.0
python        3.11.9 (C:\...\Python311\python.exe)
numpy         1.26.4
PIL           12.1.1
ffmpeg        ffmpeg version 9.0.1-full_build
ffplay        ffplay version 9.0.1-full_build
ffprobe       ffprobe version 9.0.1-full_build
terminal      120 x 40 cellules
profondeur    truecolor
rapport cell. 0.5
tty stdout    True
codec stdout  utf-8
```

Les cinq dernières lignes décrivent le terminal, pas le projet, et expliquent la plupart des
surprises de rendu :

| Ligne | Ce qu'elle contrôle |
| --- | --- |
| `terminal` | La grille disponible. `--width` est un plafond, pas une cible : il y est ramené. |
| `profondeur` | `truecolor` = 24 bits. Si c'est `none`, `--color` ne produira rien de visible. |
| `rapport cell.` | Largeur d'une cellule divisée par sa hauteur. Monte vers `0.6` si l'image paraît étirée. |
| `codec stdout` | Doit être `utf-8` pour les glyphes demi-bloc. |

`tty stdout` et `profondeur` changent selon que la sortie va vers un vrai terminal ou vers un
fichier. Redirigée, la détection renvoie `False` et `none` : c'est attendu, pas une panne.

Un guide pas à pas — prérequis, vérification, premiers rendus, dépannage — est dans
[`docs/INSTALLATION.md`](docs/INSTALLATION.md), avec une version mise en page dans
[`docs/installation.html`](docs/installation.html).

---

## Langue de l'interface

Tout ce que le programme affiche existe en français et en anglais : aide, menu, navigateur de
fichiers, sorties de `doctor` et de `list`, et messages d'erreur.

La langue est choisie dans cet ordre, le premier qui répond l'emporte :

| Priorité | Source | Exemple |
| --- | --- | --- |
| 1 | l'option `--lang` | `hachure --lang en list` |
| 2 | la variable `HACHURE_LANG` | `$env:HACHURE_LANG = "en"` |
| 3 | la locale du système | `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`, puis la langue d'affichage de Windows |
| 4 | l'anglais | si aucune source ci-dessus ne donne une langue gérée |

`--lang auto` ignore `HACHURE_LANG` et redemande une détection. Une locale comme `fr_BE@euro` ou
`French_France` est reconnue. Une locale non gérée — `de_DE`, `es_ES` — n'est jamais une erreur :
la détection passe simplement à la source suivante, donc sous un Windows en français un
`LANG=de_DE` donne du français, et de l'anglais partout ailleurs.

```powershell
hachure --lang en doctor      # ponctuellement
$env:HACHURE_LANG = "en"      # pour la session
```

La langue est aussi celle du paquet importé comme bibliothèque : les exceptions levées par
`hachure.media.image` ou `hachure.media.video` sont traduites de la même façon.

Ajouter une langue tient en une colonne : `hachure/i18n.py` associe chaque clé à un couple
`(français, anglais)`, et un test parcourt les sources pour vérifier qu'aucune clé n'est ni
manquante ni morte.

## En ligne de commande

```powershell
hachure                       # le menu interactif
hachure --lang en             # le même menu, en anglais
hachure list                  # tous les moteurs disponibles
hachure doctor                # diagnostic

hachure image photo.jpg --width 100 --color --edges --auto-levels
hachure video clip.mp4 --color --charset detailed --edges --auto-levels --fit cover --width 1000
hachure camera --color --edges
hachure demo blackhole
```

`Ctrl+C` arrête proprement toute animation, vidéo ou caméra : le curseur et les couleurs du terminal
sont restaurés dans tous les cas, y compris après une erreur.

---

## Tirer le meilleur du mode caractère

Le mode caractère est celui par défaut, et c'est tout l'intérêt du projet : l'image est faite de
caractères, et c'est ce qui produit l'effet. Trois réglages l'affinent sans jamais sortir de cette
contrainte.

### `--edges` — la plus grosse amélioration à elle seule

La luminosité seule jette la forme. Avec `--edges`, la source est échantillonnée au-dessus de la
résolution des cellules, l'orientation de contour dominante dans chaque cellule est mesurée par un
tenseur de structure, et un glyphe de ligne adapté remplace le caractère de luminosité :

| Direction du contour | Glyphe |
| --- | --- |
| horizontale | `-` |
| diagonale descendante | `\` |
| verticale | `\|` |
| diagonale montante | `/` |

Silhouettes, visages et contours sortent du bruit. Seules les cellules portant un contour fort *et*
cohérent sont remplacées : les zones plates gardent leur ton. `--edge-strength` (de 0 à 1, défaut
`0.5`) fixe la force requise — baisse-la pour plus de traits, monte-la pour moins.

Le tenseur de structure plutôt qu'un gradient moyenné, parce que des gradients opposés le long d'un
même contour s'annulent à la moyenne : exactement ce qui arrive dans une cellule à cheval sur une
ligne fine.

### `--auto-levels` et `--gamma`

La luminosité est projetée linéairement sur la rampe : une scène sombre n'atteint donc jamais les
caractères denses, ni une scène claire les caractères clairsemés. `--auto-levels` étire chaque image
sur toute la rampe, mesurée aux 2ᵉ et 98ᵉ percentiles pour que quelques pixels isolés ne définissent
pas la plage. Les niveaux glissent d'une image à l'autre, si bien que la lecture ne pulse pas quand
un élément lumineux traverse le plan.

`--gamma` remodèle les tons moyens par-dessus : au-dessus de `1` ça éclaircit, en dessous ça
assombrit. Sur une source en couleur, les deux s'appliquent comme un gain sur les trois canaux, ce
qui préserve la teinte.

### `--charset smooth`

Les rampes intégrées sont ordonnées à l'œil. `smooth` est **mesurée** : chaque glyphe ASCII
imprimable a été rendu puis noté sur sa couverture d'encre et sur la régularité de répartition de
cette encre, avant que la rampe ne soit choisie de façon à ce que ses pas soient régulièrement
espacés en couverture réelle. Les dégradés progressent proprement au lieu de vaciller entre des
caractères sosies. Les quatre glyphes de ligne sont volontairement exclus, pour rester sans
ambiguïté quand `--edges` est actif.

En calibrer une pour ta propre police :

```powershell
hachure calibrate --font "C:\Windows\Fonts\CascadiaMono.ttf" --length 12
```

### Tout mettre ensemble

```powershell
hachure video clip.mp4 --color --charset detailed --edges --auto-levels --width 1000
```

### Cellules demi-bloc

`--cells half`, ou son raccourci `--half`, tasse deux pixels empilés dans chaque cellule grâce au
demi-bloc supérieur : le premier plan peint le pixel du haut, l'arrière-plan celui du bas. Le
résultat approche la photographie, ce qui veut aussi dire qu'il cesse de ressembler à des
caractères — à utiliser quand la fidélité compte plus que l'effet. `--edges` ne s'applique pas,
puisque le glyphe est toujours le même.

### Remplir l'écran

Le rendu préserve le rapport d'image de la source : un plan en 16:9 réclame environ 3,5 colonnes par
ligne. Si le terminal a moins de lignes que ce rapport ne l'exige, la largeur est réduite et des
colonnes restent vides. Trois éléments pilotent cela :

- **`--width`** est un maximum, pas une cible. Il vaut `160` par défaut : sur un terminal large il
  faut le monter, et `--width 1000` est ramené sans risque à la largeur réelle.
- **`--fit cover`** recadre la source à la forme du terminal au lieu de l'encadrer de bandes. C'est
  ce qui rend exploitables les vidéos verticales de téléphone.
- **`--char-aspect`** indique la largeur d'une cellule par rapport à sa hauteur. `0.5` convient à la
  plupart des polices ; monte vers `0.6` si l'image paraît étirée verticalement. La variable
  d'environnement `HACHURE_CHAR_ASPECT` le règle globalement.

Redimensionner la fenêtre en cours de lecture est pris en charge : la grille est recalculée et le
flux reprend à la position courante.

---

## Rendu d'image

```powershell
hachure image IMAGE [options]

hachure image photo.png --width 120
hachure image photo.png --width 120 --output rendu.txt
hachure image photo.png --width 1000 --fit cover --half --color
```

| Option | Rôle |
| --- | --- |
| `--width N` | Largeur de sortie maximale. Défaut : `100`. |
| `--height N` | Hauteur de sortie maximale, facultative. |
| `--fit MODE` | `contain` (bandes) ou `cover` (recadre pour remplir). Défaut : `contain`. |
| `--char-aspect N` | Largeur d'une cellule divisée par sa hauteur. Défaut : `0.5`. |
| `--cells MODE` | `char` ou `half`. Défaut : `char`. |
| `--half` | Raccourci de `--cells half`. |
| `--color` / `--no-color` | Active ou désactive la couleur. Les images sont monochromes par défaut. |
| `--color-depth NOM` | `auto`, `truecolor`, `ansi256` ou `none`. |
| `--quant N` | Pas de quantification des couleurs. Défaut : `4`. |
| `--edges` | Remplace le caractère de rampe par un glyphe de ligne sur les vrais contours. |
| `--edge-strength N` | Force requise d'un contour, de `0` à `1`. Défaut : `0.5`. |
| `--auto-levels` | Étire l'image sur toute la rampe. |
| `--gamma N` | Tons moyens ; au-dessus de `1` ça éclaircit. Défaut : `1.0`. |
| `--charset NOM` | `classic`, `detailed`, `letters` ou `smooth`. |
| `--invert` | Retourne la rampe sombre-vers-clair. |
| `-o`, `--output CHEMIN` | Écrit le texte rendu dans un fichier UTF-8. |

---

## Rendu vidéo

```powershell
hachure video VIDEO [options]

hachure video clip.mp4 --no-audio
hachure video clip.mp4 --color --charset detailed --edges --auto-levels --width 1000
hachure video clip.mp4 --start 30 --duration 10 --loop
hachure video clip.mp4 --color --smoothing 0.35
hachure video clip.mp4 --color --half --record renders\clip.mp4
```

| Option | Rôle |
| --- | --- |
| `--fps N` | Cadence de lecture visée. Défaut : `20`. |
| `--width N` / `--height N` | Taille de rendu maximale en caractères. Largeur : `160` par défaut. |
| `--fit MODE` | `contain` ou `cover`. Défaut : `contain`. |
| `--cells MODE` / `--half` | Géométrie de cellule, comme ci-dessus. |
| `--color` / `--no-color` | Sortie en couleur. La vidéo est monochrome par défaut. |
| `--color-depth NOM` | Court-circuite la détection de couleur du terminal. |
| `--quant N` | Pas de quantification des couleurs. Défaut : `4`. |
| `--edges`, `--edge-strength N` | Glyphes de contour, comme ci-dessus. |
| `--auto-levels`, `--gamma N` | Mise en forme tonale, comme ci-dessus. |
| `--smoothing N` | Fondu temporel de `0` à `1` ; `1` est net, plus bas laisse des traînées. |
| `--max-frame-skip N` | Images consécutives abandonnables pour rattraper le retard. Défaut : `5`. |
| `--start N` | Position de départ en secondes. |
| `--duration N` | Arrête après ce nombre de secondes. |
| `--loop` | Redémarre quand la vidéo se termine. |
| `--no-audio` | Ne lance pas FFplay. |
| `--audio-delay N` | Décale l'audio de -30 à +30 s ; une valeur positive le retarde. |
| `--record CHEMIN` | Écrit la sortie rendue en `.mp4` ou `.gif`. |
| `--charset NOM`, `--invert` | Rampe de caractères, comme ci-dessus. |

Les métadonnées de rotation sont respectées : un plan filmé en portrait au téléphone est mesuré et
rendu droit, plutôt qu'écrasé.

```text
                       ┌─ FFmpeg → images brutes mises à l'échelle → NumPy → cellules → terminal
vidéo source ──────────┤
                       └─ FFplay → audio
```

Le moteur suit un calendrier à l'horloge murale. Quand le rendu prend du retard, il abandonne un
nombre borné d'images décodées au lieu de laisser la dérive s'installer.

---

## Capture caméra

```powershell
hachure camera --list
hachure camera --color --half
hachure camera --device "Integrated Webcam" --size 1280x720 --duration 10 --record me.gif
```

L'entrée caméra passe par DirectShow sous Windows, AVFoundation sous macOS et Video4Linux2 sous
Linux. L'audio n'est jamais capturé. Si une caméra listée refuse de s'ouvrir sous Windows, autorise
les applications de bureau dans *Paramètres → Confidentialité et sécurité → Caméra*, et ferme tout
ce qui l'utilise déjà.

---

## Enregistrement

`--record CHEMIN` peint chaque image rendue avec une police à chasse fixe et redirige le résultat
vers FFmpeg. Les séquences d'échappement sont relues au cours de cette passe : les enregistrements
gardent donc leurs couleurs.

| Option | Rôle |
| --- | --- |
| `--record CHEMIN` | Destination ; `.gif` produit un GIF animé, tout le reste une vidéo H.264. |
| `--font CHEMIN` | `.ttf` à chasse fixe pour peindre. Une police système est trouvée automatiquement. |
| `--font-size N` | Corps de la police, qui fixe la résolution de sortie. Défaut : `16`. |

Disponible pour `video`, `camera` et `demo`.

---

## Démos procédurales

Cinq scènes calculées en temps réel, sans source externe : projection, éclairage et tampon de
profondeur écrits à la main.

```powershell
hachure demo NOM [options]

hachure demo donut --fps 30
hachure demo planet --width 120 --charset detailed
hachure demo blackhole --width 140 --record blackhole.gif
```

| Démo | Technique |
| --- | --- |
| `cube` | Rotation des sommets, projection en perspective, normales de face, élimination des faces arrière, remplissage de triangles, tampon de profondeur interpolé. |
| `sphere` | Reconstruction de la sphère cellule par cellule et éclairage directionnel. |
| `donut` | Échantillonnage d'un tore paramétrique, éclairage par les normales, perspective, tampon de profondeur. |
| `planet` | Sphère en rotation, relief procédural, face nocturne, halo atmosphérique. |
| `blackhole` | Disque d'accrétion en coordonnées polaires, étoiles déterministes, lueur asymétrique, effet d'anneau de photons. |

Toutes acceptent `--width`, `--height`, `--fps`, `--charset`, `--invert` et les options
d'enregistrement. Les dimensions sont réduites au besoin pour tenir dans le terminal, et la scène se
recompose quand la fenêtre est redimensionnée.

---

## Couleurs

La profondeur de couleur est déduite de `COLORTERM`, de `TERM` et du terminal hôte, et `NO_COLOR`
est respecté. `--color-depth` court-circuite le résultat :

- `truecolor` — premier plan et arrière-plan sur 24 bits. Windows Terminal, VS Code, la plupart des
  émulateurs modernes.
- `ansi256` — la palette xterm-256, pour les terminaux plus anciens.
- `none` — monochrome.

`--quant` aligne les valeurs de canal sur un pas avant leur émission. Des valeurs plus grandes
produisent de plus longues plages de couleur identique, donc moins de séquences d'échappement — ce
qui compte sur un terminal lent.

---

## Notes de performance

- Les séquences d'échappement sont construites depuis des préfixes en cache et émises **par plage**
  plutôt que par cellule, et seules les lignes réellement modifiées sont repeintes.
- Monter `--quant`, baisser `--fps` ou baisser `--width` sont les leviers efficaces quand la lecture
  saccade, dans cet ordre.
- Les demi-cellules doublent le nombre de pixels : elles coûtent environ deux fois plus par image
  que les cellules `char`, à grille égale.
- `--edges` échantillonne trois pixels par côté de cellule, donc FFmpeg décode neuf fois plus de
  pixels. Sur une grille de terminal normale cela reste faible, mais c'est la seule option qui
  augmente le coût de **décodage** et pas seulement celui du rendu.

---

## Développement

```powershell
python -m unittest discover -s tests -v    # suite complète, comme la CI
python -m pytest                           # équivalent
python -m pytest tests/test_render.py -k half
python -m unittest tests.test_render.RenduMonochromeTests
```

223 tests, moins de trois secondes. Aucun n'ouvre de vrai terminal ni ne lit de vrai fichier média : les
appels FFmpeg sont simulés, les touches du menu et les saisies clavier le sont aussi, et les rendus
sont comparés sur de petits tableaux NumPy construits à la main.

Ni linter ni formateur configuré. La CI lance la suite sur Python 3.10 et 3.14, puis vérifie que
`hachure --version` et `hachure list` répondent.

**Le code, les commentaires, la documentation et les noms de tests sont en français**, tandis que
**l'interface est bilingue** : aucun texte affiché n'est écrit en dur, tout passe par `i18n.py`.

Trois exceptions, marquées par un commentaire à leur emplacement : les sous-chaînes comparées à la
sortie de FFmpeg ; les messages internes d'argparse et d'unittest, qui passent par gettext sans
catalogue français dans CPython ; et deux `OSError` de `terminal.py`, attrapées sur place et jamais
affichées.

Un test qui vérifie un texte affiché doit fixer la langue explicitement — sinon il passe sur une
machine française et échoue sur la CI, qui tourne en anglais.

### Architecture

Tout converge vers un point de conversion unique. Deux familles de sources — pixels décodés,
géométrie procédurale — et trois sorties — terminal, fichier texte, vidéo enregistrée — se
rejoignent dans `render.py`.

```text
media/image.py (Pillow) ─┐
media/video.py (FFmpeg) ─┼→ tableau NumPy → tone.py → edges.py → render.py → texte ANSI ─┬→ terminal.py
renderers/*.py ──────────┘   (les démos émettent du texte directement)        color.py   └→ export.py
```

| Module | Rôle |
| --- | --- |
| `render.py` | Le pivot. `RenderStyle` porte rampe, mode de cellule, profondeur de couleur, quantification et contours. Ses `pixel_cols()`/`pixel_rows()` disent au décodeur *en amont* combien de pixels réclame une grille de caractères. La sortie est bâtie en plages compressées par ligne, jamais cellule par cellule — et une plage ne franchit jamais une frontière de ligne, pour que chaque ligne reste redessinable seule. |
| `edges.py` | Suréchantillonne 3× par côté de cellule et choisit `-`, `\`, `\|` ou `/` via un tenseur de structure. Les glyphes de contour sont rangés après la fin de la rampe, si bien que l'aval indexe un alphabet unique sans cas particulier. |
| `tone.py` | Niveaux automatiques et gamma. À état entre les images : `reset()` sur un saut ou un redémarrage de boucle. |
| `color.py` | Mémoïse les préfixes ANSI, indexés par RVB compacté. Détecte la profondeur via `NO_COLOR`, `COLORTERM`, `TERM`. |
| `terminal.py` | Dimensionnement et boucle d'animation. `Screen.draw()` ne repeint que les lignes modifiées. `terminal_session()` garantit la restauration du curseur et des couleurs. |
| `media/video.py` | Construit la commande FFmpeg, lit des images brutes de taille fixe, suit un calendrier à l'horloge murale. L'audio est un processus FFplay distinct. |
| `renderers/` | Démos autonomes enregistrées dans un dictionnaire `DEMOS`. Ajouter une démo = un module plus une entrée. |
| `export.py` | Réanalyse les codes ANSI reçus et les repeint avec une police à chasse fixe, vers FFmpeg. |
| `menu.py` | Le menu. Ne duplique aucune option : il compose une liste d'arguments et la passe à `main()`. |
| `i18n.py` | Le catalogue bilingue et la détection de langue. Un dictionnaire, pas gettext : rien à compiler. |
| `cli.py` | Argparse seulement. Les groupes d'options sont partagés entre sous-commandes. |

NumPy et Pillow sont importés paresseusement, et les fonctions manipulant des tableaux reçoivent
`np` en paramètre explicite plutôt que de l'importer au niveau du module.

---

## Crédits

`hachure` dérive de [ASCII-Art](https://github.com/RipperdocNiladri/ASCII-Art), publié sous licence
MIT par **Niladri Pal** et **Talal Alqahs**. Le rendu, la CLI et le menu ont été réécrits depuis,
mais la notice de copyright d'origine est conservée dans [`LICENSE`](LICENSE), comme la licence MIT
l'exige.

Distribué sous licence MIT.
