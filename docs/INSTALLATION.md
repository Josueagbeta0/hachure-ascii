# Mise en route de hachure

Installer le projet, vérifier la chaîne de rendu et produire un premier rendu en terminal.

> Une version mise en page de ce guide est disponible dans [`installation.html`](installation.html) —
> ouvrable directement dans un navigateur.

**Sommaire** — [Pré-requis](#01--pré-requis) · [Installation](#02--installation) ·
[Vérification](#03--vérification) · [Premiers rendus](#04--premiers-rendus) ·
[Développement](#05--développement) · [Dépannage](#06--dépannage) ·
[Options clés](#07--options-clés)

---

## 01 · Pré-requis

Deux paquets Python, installés automatiquement, et un outil externe. Rien d'externe n'est requis
pour la conversion d'images : FFmpeg ne sert qu'à la vidéo et à la caméra.

| Composant | Rôle |
| --- | --- |
| **Python ≥ 3.10** | La CI valide 3.10 et 3.14. NumPy et Pillow s'installent automatiquement. |
| **ffmpeg** | Décode la vidéo et la caméra en trames brutes envoyées sur `stdout`. |
| **ffprobe** | Lit les dimensions et la rotation de la source, pour qu'une vidéo filmée verticalement soit redressée plutôt qu'écrasée. |
| **ffplay** | Lit la piste audio en parallèle du rendu. Facultatif : `--no-audio` s'en passe. |
| **Police monospace** | Doit contenir `▀` et `▄` pour le mode demi-bloc. Cascadia Mono, Consolas, DejaVu Sans Mono et Menlo conviennent. |
| **Terminal truecolor** | Windows Terminal, VS Code ou tout émulateur moderne, pour `--color` en 24 bits. |

### Installer FFmpeg

Les trois binaires viennent ensemble. Après l'installation, **rouvre le terminal** pour que le
`PATH` soit rechargé.

```powershell
# Windows
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg
```

---

## 02 · Installation

Un environnement virtuel par projet, puis une installation éditable : le code reste vivant, une
modification d'un fichier source est prise en compte sans réinstaller.

```powershell
# Windows · PowerShell, depuis la racine du dépôt
cd "C:\dev\hachure-ascii"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

```bash
# macOS / Linux
cd hachure-ascii
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Les guillemets autour de `".[dev]"` sont nécessaires : PowerShell interprète les crochets nus. Si
le chemin de ton projet contient un espace ou des parenthèses, garde-le **entre guillemets** dans
toutes les commandes.

| Élément | Rôle |
| --- | --- |
| `.venv` | Isole numpy, Pillow et pytest du Python système. Le dossier est déjà ignoré par git. |
| `-e` | Installation éditable : le paquet pointe vers les sources au lieu d'en copier une version figée. |
| `[dev]` | Extra facultatif du `pyproject.toml` ; ajoute pytest. Sans lui, la suite de tests reste lançable via `unittest`. |

**Si `Activate.ps1` est bloqué.** Windows refuse par défaut l'exécution de scripts non signés.
Autorise-la pour la session courante uniquement — aucune trace au-delà de la fenêtre :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Sans activer l'environnement.** Tu peux toujours appeler les binaires directement :
`.\.venv\Scripts\hachure.exe` ou `.\.venv\Scripts\python.exe -m hachure`.

---

## 03 · Vérification

Une seule commande couvre toute la chaîne : versions Python et bibliothèques, présence des trois
outils FFmpeg, taille du terminal, profondeur de couleur détectée et encodage de sortie. C'est le
premier réflexe dès qu'un rendu se comporte mal.

```text
> hachure doctor
hachure       0.3.0
python        3.11.9 (...\hachure-ascii\.venv\Scripts\python.exe)
numpy         2.4.6
PIL           12.3.0
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
| `terminal` | La grille disponible. `--width` est un plafond, pas une cible : il est ramené à cette largeur. |
| `profondeur` | `truecolor` = 24 bits. Si la valeur est `none`, `--color` ne produira rien de visible. |
| `rapport cell.` | Largeur d'une cellule divisée par sa hauteur. `0.5` convient à la plupart des polices ; monte vers `0.6` si l'image paraît étirée verticalement. |
| `codec stdout` | Doit être `utf-8` pour les glyphes demi-bloc. Voir le dépannage si tu vois `cp1252`. |

> **Deux valeurs qui dépendent du contexte.** `tty stdout` et `profondeur` changent selon que la
> sortie va vers un vrai terminal ou vers un fichier. Redirigée, la détection renvoie `False` et
> `none` — c'est le comportement attendu, pas une panne.

Enfin, `hachure list` énumère les moteurs de rendu disponibles : trois entrées (image, video,
camera) et cinq démos procédurales.

---

## 04 · Premiers rendus

<kbd>Ctrl</kbd>+<kbd>C</kbd> arrête proprement toute animation, vidéo ou caméra : le curseur et les
couleurs du terminal sont restaurés dans tous les cas, y compris après une erreur.

### Le plus simple : le menu

Sans rien connaître des options, tape la commande seule :

```powershell
hachure
```

```text
hachure · rendu d'images, de vidéos et de 3D en caractères

  Image fixe          convertir une photo en caractères
  Vidéo               lire un fichier vidéo
  Caméra              diffuser une caméra en direct
  Démo procédurale    cube, sphère, tore, planète, trou noir
  Diagnostic          dépendances et capacités du terminal
  Moteurs disponibles ce que le projet sait rendre
  Calibrer une rampe  mesurer une police à chasse fixe
  Quitter

↑↓ déplacer · Entrée valider · Échap revenir
```

Flèches ↑ ↓ pour se déplacer, `Entrée` pour valider, `Échap` pour revenir.

**Rien ne se tape.** Choisis une source et un navigateur de fichiers s'ouvre, filtré sur les formats
que la commande sait lire, avec la taille de chaque fichier :

```text
Quelle vidéo ?
C:\Users\moi\Videos

› ..                     dossier parent
  archives/              dossier
  concert.mp4            84.2 Mo
  timelapse.mkv          12.7 Mo
  [ changer de disque ]
  [ annuler ]
```

`..` remonte d'un cran, un dossier s'ouvre, un fichier se choisit. Les dossiers trop grands sont
bornés, et le dernier dossier visité est mémorisé pour l'ouverture suivante.

Vient ensuite l'écran de réglages, où chaque ligne se change sans jamais saisir de valeur :
`Espace` ou ← → passent à la valeur suivante, `Entrée` ouvre la liste complète. Une valeur laissée
sur `défaut` n'est pas transmise — c'est le défaut de la CLI qui s'applique, jamais une copie figée
dans le menu.

```text
Réglages · video

  Largeur maximale     160
  Ajustement           cover
› Contours (--edges)   oui
  Jeu de caractères    detailed
  Durée en secondes    30
  Enregistrer le rendu concert-20260916-205412.mp4

  Lancer le rendu
  Annuler

hachure … --width 160 --fit cover --edges --charset detailed --duration 30 …
```

Pour une destination d'enregistrement, le navigateur sert à désigner un **dossier**, puis un nom est
proposé à partir du nom de la source — avec une variante horodatée, pour ne pas écraser un rendu
précédent sans le vouloir.

La dernière ligne est le point important : le menu ne fait que **composer une ligne de commande**,
il te la montre, puis il la joue. C'est aussi la façon la plus rapide d'apprendre les options
décrites plus bas.

> **Hors terminal.** Redirigée vers un pipe ou un fichier — ce qui inclut Git Bash, dont Python ne
> reconnaît pas le terminal —, la navigation aux flèches n'est pas possible : le menu affiche alors
> des listes numérotées et lit les réponses ligne par ligne.

### Image fixe

Les exemples ci-dessous prennent `photo.png` et `clip.mp4` : remplace-les par tes propres
fichiers, ou laisse le navigateur du menu les trouver.

```powershell
# rendu simple
hachure image photo.png --width 100

# le meilleur rendu en caractères : bords + plage tonale complète
hachure image photo.png --width 100 --color --edges --auto-levels

# écrire dans un fichier texte UTF-8 plutôt que dans le terminal
hachure image photo.png --width 120 -o out\photo.txt
```

### Vidéo

```powershell
# lecture avec audio
hachure video clip.mp4

# le réglage recommandé, en plein écran
hachure video clip.mp4 --color --charset detailed --edges --auto-levels --width 1000

# un extrait de 10 s à partir de 0:30, en boucle, sans audio
hachure video clip.mp4 --start 30 --duration 10 --loop --no-audio

# enregistrer ce qui est rendu
hachure video clip.mp4 --color --half --record out\clip.mp4
```

> **Pourquoi `--width 1000`.** `--width` vaut 160 par défaut et agit comme un maximum. Sur un
> terminal large, une valeur volontairement trop grande est simplement ramenée à la largeur réelle
> — c'est la façon normale de remplir la fenêtre. `--fit cover` recadre en plus la source à la
> forme du terminal, ce qui rend exploitable une vidéo verticale.

### Caméra

```text
> hachure camera --list
Caméras :
  Integrated Webcam
  LSVCam
```

```powershell
hachure camera --color --edges
hachure camera --device "Integrated Webcam" --size 1280x720 --duration 10 --record out\me.gif
```

### Démos procédurales

Cinq scènes calculées en temps réel, sans source externe : projection, éclairage et tampon de
profondeur écrits à la main.

```powershell
hachure demo donut --fps 30
hachure demo planet --width 120 --charset detailed
hachure demo blackhole --width 140 --record out\blackhole.gif
```

Les autres noms sont `cube` et `sphere`. Toutes les démos acceptent `--width`, `--height`, `--fps`,
`--charset`, `--invert` et les options d'enregistrement, et se recomposent quand la fenêtre est
redimensionnée.

---

## 05 · Développement

### Lancer les tests

197 tests, moins d'une seconde. Aucun n'ouvre de vrai terminal ni ne lit de vrai fichier média :
les appels FFmpeg sont simulés, les touches du menu et les saisies clavier le sont aussi, et les
rendus sont comparés sur de petits tableaux NumPy construits à la main.

```text
> python -m unittest discover -s tests
.....................................................................................................................................................................................................
----------------------------------------------------------------------
Ran 197 tests in 0.377s

OK
```

| Commande | Portée |
| --- | --- |
| `python -m unittest discover -s tests -v` | Suite complète, exactement comme la CI. |
| `python -m pytest` | Équivalent. Les tests sont écrits en `unittest` mais pytest les exécute. |
| `python -m pytest tests/test_render.py -k half` | Un fichier, filtré par motif. |
| `python -m unittest tests.test_render.RenduMonochromeTests` | Une classe isolée. |
| `python -W error::DeprecationWarning -m unittest discover -s tests` | Forme stricte de la CI : tout `DeprecationWarning` devient une erreur. |

> **Ni linter ni formateur.** Le projet n'en configure aucun. La CI lance la suite sur Python 3.10
> et 3.14, puis vérifie que `hachure --version` et `hachure list` répondent.

### Calibrer une rampe sur ta police

Les rampes intégrées sont ordonnées à l'œil, sauf `smooth` qui est mesurée. La commande `calibrate`
rend chaque glyphe ASCII imprimable, mesure sa couverture d'encre réelle et construit une rampe
dont les paliers sont régulièrement espacés.

```powershell
hachure calibrate --font "C:\Windows\Fonts\CascadiaMono.ttf" --length 12
```

Le résultat s'ajoute à `CHARSETS` dans `hachure/charsets.py` pour devenir accessible via
`--charset`.

### Publier une version

Le workflow de publication compare `__version__`, dans `hachure/__init__.py`, au tag de
la release privé de son préfixe `v`. **Les deux doivent correspondre**, sinon le build échoue avant
même la construction du paquet.

---

## 06 · Dépannage

Les situations réellement rencontrées, dans l'ordre où elles se présentent.

### `hachure` : commande introuvable

L'environnement n'est pas activé, ou le dossier `Scripts` n'est pas dans le `PATH`. La forme module
fonctionne toujours : `python -m hachure list`.

### « FFmpeg est introuvable dans le PATH »

FFmpeg est installé mais le terminal a été ouvert avant. Ferme-le et rouvre-le, puis confirme avec
`hachure doctor`. Le message équivalent pour l'audio se contourne avec `--no-audio`.

### « 'charmap' codec can't encode characters »

Sur Windows, une sortie **redirigée** retombe sur la page de codes cp1252, qui ne connaît pas `▀`.
Le cas se produit avec `--half` envoyé vers un fichier ou un pipe. Deux sorties :

```powershell
# -o écrit explicitement en UTF-8
hachure image photo.png --half -o out\photo.txt

# ou forcer l'encodage de sortie
$env:PYTHONIOENCODING = "utf-8"
```

### L'image paraît étirée ou écrasée

La correction d'aspect ne correspond pas à ta police. Monte `--char-aspect` vers `0.6` si le rendu
est étiré en hauteur. La variable d'environnement `HACHURE_CHAR_ASPECT` fixe la valeur une fois
pour toutes.

### Des colonnes vides sur les côtés

Le ratio de la source est préservé : un clip 16:9 réclame environ 3,5 colonnes par ligne. Si le
terminal n'a pas assez de lignes, la largeur est réduite. Augmente `--width`, ou passe en
`--fit cover` pour recadrer au lieu de laisser des bandes.

### `pip list` affiche une version périmée

Une installation éditable fige les métadonnées au moment de l'installation : `pip list` peut
annoncer `0.2.0` alors que `hachure --version` répond `0.3.0`. C'est `--version` qui dit vrai,
puisqu'il lit le code en direct. Un `pip install -e ".[dev]"` rafraîchit l'étiquette.

### La lecture saccade

Dans l'ordre d'efficacité : monter `--quant`, baisser `--fps`, baisser `--width`. À garder en
tête : `--half` double le nombre de pixels par trame, et `--edges` échantillonne neuf fois plus de
pixels — c'est la seule option qui alourdit le décodage et pas seulement le rendu.

---

## 07 · Options clés

Les réglages qui changent vraiment le résultat. Tous valent pour `image`, `video` et `camera`,
sauf `--smoothing`, qui n'a de sens que sur un flux et n'existe donc que pour `video` et `camera`.

| Option | Défaut | Effet |
| --- | --- | --- |
| `--edges` | off | Le gain le plus important. L'orientation dominante du contour dans chaque cellule remplace le caractère de luminosité par `-`, `\`, `\|` ou `/`. Les silhouettes ressortent. |
| `--auto-levels` | off | Étire chaque trame sur toute la rampe au lieu de la bande étroite qu'elle occupe. Mesuré aux 2ᵉ et 98ᵉ percentiles, lissé entre les trames. |
| `--charset` | `classic` | `classic`, `detailed`, `letters` ou `smooth`. `smooth` est calibrée sur la couverture d'encre réelle et exclut les quatre glyphes de contour. |
| `--half` | off | Deux pixels empilés par cellule. Se rapproche de la photo, mais cesse de ressembler à des caractères — incompatible avec `--edges`. |
| `--fit` | `contain` | `cover` recadre la source à la forme du terminal au lieu de la laisser en bandes. |
| `--gamma` | `1.0` | Reprofile les tons moyens : au-dessus de 1 éclaircit. Sur une source couleur, appliqué en gain sur les trois canaux, ce qui préserve la teinte. |
| `--quant` | `4` | Pas de quantification couleur. Plus il est grand, plus les séquences d'échappement sont rares — le levier principal sur un terminal lent. |
| `--smoothing` | `1.0` | *(`video` et `camera` seulement)* Fondu temporel entre trames. 1 est net ; descendre vers 0,35 laisse des traînées de mouvement. |

### La combinaison à retenir

Pour la vidéo, ces quatre options ensemble donnent le rendu en caractères le plus lisible que le
projet sache produire — sans jamais quitter la contrainte du caractère :

```powershell
hachure video clip.mp4 --color --charset detailed --edges --auto-levels --width 1000
```
