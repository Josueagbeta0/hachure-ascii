"""Menu interactif, lancé quand « hachure » est appelé sans argument.

Le menu ne réimplémente aucune option : il compose une ligne de commande, la
montre, puis la confie au parseur argparse habituel. La CLI reste donc la seule
source de vérité sur les drapeaux et leurs valeurs par défaut, et l'utilisateur
repart en sachant quelle commande il vient de jouer.

Sur un terminal, **rien ne se tape** : les fichiers se choisissent dans un
navigateur d'arborescence, les valeurs numériques dans des listes de réglages
courants, et les destinations d'enregistrement en désignant un dossier puis un
nom proposé. Tout passe donc par la même primitive de sélection.

Dès que l'entrée ou la sortie est redirigée, la navigation aux flèches devient
impossible : tout retombe alors sur des listes numérotées et des chemins tapés,
lus avec ``input()``. C'est ce second mode que les tests exercent, ce qui évite
d'ouvrir un vrai terminal.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from hachure.charsets import CHARSETS, DEFAULT_CHARSET
from hachure.color import detect_color_depth
from hachure.render import CELL_MODES
from hachure.renderers import DEMOS
from hachure.terminal import FIT_MODES, terminal_size

QUITTER = "quitter"

_INVITE_TOUCHES = "↑↓ déplacer · Entrée valider · Échap revenir"
_INVITE_REGLAGES = "↑↓ déplacer · Espace/←→ changer · Entrée ouvrir · Échap revenir"


# --------------------------------------------------------------------------- #
# Lecture des touches
# --------------------------------------------------------------------------- #


def interactif() -> bool:
    """Vrai seulement si l'on peut à la fois dessiner et lire des touches."""
    return bool(
        getattr(sys.stdin, "isatty", lambda: False)()
        and getattr(sys.stdout, "isatty", lambda: False)()
    )


def _lire_touche_windows() -> str:
    import msvcrt

    touche = msvcrt.getwch()
    # Les touches de direction arrivent en deux temps, précédées d'un préfixe.
    if touche in ("\x00", "\xe0"):
        suite = msvcrt.getwch()
        return {"H": "haut", "P": "bas", "K": "gauche", "M": "droite"}.get(suite, "")
    return {"\r": "entree", "\n": "entree", "\x1b": "echap", "\x03": "interruption"}.get(
        touche, touche
    )


def _lire_touche_posix() -> str:
    import termios
    import tty

    descripteur = sys.stdin.fileno()
    reglages = termios.tcgetattr(descripteur)
    try:
        tty.setraw(descripteur)
        touche = sys.stdin.read(1)
        if touche == "\x1b":
            # Une séquence CSI complète, ou un Échap isolé si rien ne suit.
            if sys.stdin.read(1) != "[":
                return "echap"
            return {"A": "haut", "B": "bas", "D": "gauche", "C": "droite"}.get(
                sys.stdin.read(1), ""
            )
    finally:
        termios.tcsetattr(descripteur, termios.TCSADRAIN, reglages)
    return {"\r": "entree", "\n": "entree", "\x03": "interruption"}.get(touche, touche)


def lire_touche() -> str:
    """Lit une touche et la ramène à un nom logique.

    Renvoie ``haut``, ``bas``, ``gauche``, ``droite``, ``entree``, ``echap``,
    ``interruption``, sinon le caractère brut.
    """
    if sys.platform == "win32":
        return _lire_touche_windows()
    return _lire_touche_posix()


# --------------------------------------------------------------------------- #
# Dessin
# --------------------------------------------------------------------------- #


class _Zone:
    """Bloc de lignes repeint sur place, pour ne pas remplir l'historique.

    Le nombre de lignes est compté sur le texte réellement écrit, pas sur la
    liste reçue : un libellé peut contenir un saut de ligne. Les appelants
    raccourcissent en revanche chaque ligne à la largeur du terminal, car un
    repli visuel ne se compte pas et décalerait le repeint.
    """

    __slots__ = ("_lignes",)

    def __init__(self) -> None:
        self._lignes = 0

    def effacer(self) -> None:
        if self._lignes:
            sys.stdout.write(f"\033[{self._lignes}A")
        sys.stdout.write("\r\033[J")
        sys.stdout.flush()
        self._lignes = 0

    def dessiner(self, lignes: Sequence[str]) -> None:
        self.effacer()
        bloc = "\n".join(lignes)
        sys.stdout.write(bloc + "\n")
        sys.stdout.flush()
        self._lignes = bloc.count("\n") + 1


class _Style:
    """Habillage ANSI, neutralisé quand le terminal n'a pas de couleur."""

    __slots__ = ("actif",)

    def __init__(self) -> None:
        self.actif = detect_color_depth() != "none"

    def selection(self, texte: str) -> str:
        return f"\033[7m{texte}\033[0m" if self.actif else f"› {texte}"

    def normal(self, texte: str) -> str:
        # Deux colonnes de marge, pour rester aligné avec le marqueur « › ».
        return f"  {texte}"

    def discret(self, texte: str) -> str:
        return f"\033[2m{texte}\033[0m" if self.actif else texte


def _raccourcir(texte: str, largeur: int) -> str:
    """Ramène un texte à ``largeur`` colonnes en élidant le milieu.

    Le milieu plutôt que la fin : sur un chemin, le début situe et la fin nomme,
    c'est le segment intermédiaire qui est le moins utile.
    """
    if len(texte) <= largeur:
        return texte
    if largeur <= 1:
        return texte[:largeur]
    reste = largeur - 1
    tete = (reste + 1) // 2
    queue = reste - tete
    return texte[:tete] + "…" + (texte[-queue:] if queue else "")


def _debut_fenetre(curseur: int, total: int, hauteur: int) -> int:
    """Premier rang visible, en gardant le curseur au centre quand c'est possible."""
    if total <= hauteur:
        return 0
    return max(0, min(curseur - hauteur // 2, total - hauteur))


def _dessiner_liste(
    zone: _Zone,
    style: _Style,
    titre: str,
    rangs: Sequence[str],
    curseur: int,
    bas: Sequence[str],
) -> None:
    """Dessine un titre, une fenêtre défilante de rangs, puis des lignes de pied.

    La fenêtre est indispensable : un dossier peut contenir bien plus d'entrées
    que le terminal n'a de lignes, et un bloc plus haut que l'écran ferait
    défiler la console, ce qui casserait le repeint en place.
    """
    colonnes, lignes_terminal = terminal_size()
    largeur = max(20, colonnes - 4)
    lignes_titre = [_raccourcir(ligne, largeur) for ligne in titre.split("\n")]

    # Titre, ligne vide, pied, plus une marge : on ne remplit jamais l'écran.
    hauteur = max(3, lignes_terminal - len(lignes_titre) - len(bas) - 4)
    debut = _debut_fenetre(curseur, len(rangs), hauteur)
    visibles = rangs[debut : debut + hauteur]

    sortie = [*lignes_titre, ""]
    if debut:
        sortie.append(style.discret(f"  ↑ {debut} au-dessus"))
    for decalage, texte in enumerate(visibles):
        court = _raccourcir(texte, largeur)
        sortie.append(
            style.selection(court) if debut + decalage == curseur else style.normal(court)
        )
    restant = len(rangs) - debut - len(visibles)
    if restant > 0:
        sortie.append(style.discret(f"  ↓ {restant} en dessous"))
    sortie.append("")
    sortie += [style.discret(_raccourcir(ligne, largeur)) for ligne in bas]
    zone.dessiner(sortie)


# --------------------------------------------------------------------------- #
# Sélection dans une liste
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Entree:
    """Une ligne sélectionnable : un libellé, une explication, une valeur."""

    libelle: str
    valeur: object
    detail: str = ""


def _selection_numerotee(titre: str, entrees: Sequence[Entree]) -> object | None:
    print(f"\n{titre}")
    for rang, entree in enumerate(entrees, start=1):
        suffixe = f" — {entree.detail}" if entree.detail else ""
        print(f"  {rang}. {entree.libelle}{suffixe}")
    while True:
        print("Choix (vide pour revenir) :")
        try:
            saisie = _lire_ligne().strip()
        except EOFError:
            return None
        if not saisie:
            return None
        if saisie.isdigit() and 1 <= int(saisie) <= len(entrees):
            return entrees[int(saisie) - 1].valeur
        print(f"Entrez un nombre entre 1 et {len(entrees)}.")


def selectionner(titre: str, entrees: Sequence[Entree]) -> object | None:
    """Fait choisir une entrée. Renvoie sa valeur, ou None si l'on revient."""
    if not entrees:
        return None
    if not interactif():
        return _selection_numerotee(titre, entrees)

    style = _Style()
    zone = _Zone()
    curseur = 0
    largeur = max(len(entree.libelle) for entree in entrees)
    rangs = [
        f"{entree.libelle.ljust(largeur)}  {entree.detail}".rstrip()
        for entree in entrees
    ]
    while True:
        _dessiner_liste(zone, style, titre, rangs, curseur, [_INVITE_TOUCHES])

        touche = lire_touche()
        if touche == "haut":
            curseur = (curseur - 1) % len(entrees)
        elif touche == "bas":
            curseur = (curseur + 1) % len(entrees)
        elif touche == "entree":
            zone.effacer()
            return entrees[curseur].valeur
        elif touche in ("echap", "interruption", "q"):
            zone.effacer()
            return None


# --------------------------------------------------------------------------- #
# Champs de réglage
# --------------------------------------------------------------------------- #

_DEFAUT = "défaut"


@dataclass
class Bascule:
    """Un drapeau sans valeur, présent ou absent."""

    drapeau: str
    libelle: str
    actif: bool = False

    def affichage(self) -> str:
        return "oui" if self.actif else "non"

    def modifier(self, sens: int) -> None:
        self.actif = not self.actif

    def ouvrir(self) -> None:
        self.modifier(1)

    def argv(self) -> list[str]:
        return [self.drapeau] if self.actif else []


@dataclass
class Choix:
    """Un drapeau à valeur prise dans une liste fermée.

    Une valeur vide signifie « garder le défaut de la CLI » : rien n'est émis,
    ce qui évite au menu de recopier les valeurs par défaut d'argparse.
    """

    drapeau: str
    libelle: str
    valeurs: tuple[str, ...]
    rang: int = 0

    def affichage(self) -> str:
        return self.valeurs[self.rang] or _DEFAUT

    def modifier(self, sens: int) -> None:
        self.rang = (self.rang + sens) % len(self.valeurs)

    def ouvrir(self) -> None:
        """Ouvre la liste complète, plus lisible qu'un défilement à l'aveugle."""
        choisi = selectionner(
            self.libelle,
            [Entree(valeur or _DEFAUT, rang) for rang, valeur in enumerate(self.valeurs)],
        )
        if choisi is not None:
            self.rang = int(choisi)

    def argv(self) -> list[str]:
        valeur = self.valeurs[self.rang]
        return [self.drapeau, valeur] if valeur else []


@dataclass
class Fichier:
    """Un drapeau désignant un fichier existant, choisi dans le navigateur."""

    drapeau: str
    libelle: str
    extensions: tuple[str, ...] | None = None
    valeur: str = ""

    def affichage(self) -> str:
        return Path(self.valeur).name if self.valeur else "aucun"

    def modifier(self, sens: int) -> None:
        return None

    def ouvrir(self) -> None:
        choisi = choisir_fichier(self.libelle, self.extensions)
        if choisi is not None:
            self.valeur = choisi

    def argv(self) -> list[str]:
        return [self.drapeau, self.valeur] if self.valeur else []


@dataclass
class Sortie:
    """Un drapeau de destination : un dossier désigné, puis un nom proposé.

    Le fichier n'existe pas encore, donc le navigateur ne peut pas le pointer ;
    les noms sont fabriqués à partir de ``base`` et des extensions permises, de
    sorte qu'il n'y ait jamais rien à taper.
    """

    drapeau: str
    libelle: str
    extensions: tuple[str, ...]
    base: str = "rendu"
    valeur: str = ""

    def affichage(self) -> str:
        return Path(self.valeur).name if self.valeur else "aucun"

    def modifier(self, sens: int) -> None:
        return None

    def ouvrir(self) -> None:
        choisi = choisir_destination(self.libelle, self.base, self.extensions)
        if choisi is not None:
            self.valeur = choisi

    def argv(self) -> list[str]:
        return [self.drapeau, self.valeur] if self.valeur else []


Champ = Bascule | Choix | Fichier | Sortie


def _argv_des_champs(champs: Sequence[Champ]) -> list[str]:
    arguments: list[str] = []
    for champ in champs:
        arguments += champ.argv()
    return arguments


# --------------------------------------------------------------------------- #
# Saisies, réservées au mode sans terminal
# --------------------------------------------------------------------------- #


def _lire_ligne(invite: str = "") -> str:
    """Lit une ligne d'entrée, débarrassée de sa marque d'ordre des octets.

    PowerShell préfixe un BOM UTF-8 à tout stdin redirigé, et ``str.strip()`` ne
    considère pas ``\ufeff`` comme une espace : sans ce nettoyage, la première
    réponse envoyée par un pipe est toujours rejetée.
    """
    return input(invite).lstrip("\ufeff")


def _demander_ligne(invite: str) -> str | None:
    """Lit une ligne. Renvoie None si l'entrée est fermée."""
    try:
        if interactif():
            return _lire_ligne(f"{invite} : ")
        # Sans terminal, la saisie n'est pas réaffichée : une invite par ligne
        # évite que toutes les questions se collent les unes aux autres.
        print(f"{invite} :")
        return _lire_ligne()
    except EOFError:
        return None


def _nettoyer_chemin(brut: str) -> str:
    """Retire les guillemets qu'ajoute un glisser-déposer dans la console."""
    nettoye = brut.strip()
    for guillemet in ('"', "'"):
        if len(nettoye) >= 2 and nettoye.startswith(guillemet) and nettoye.endswith(guillemet):
            nettoye = nettoye[1:-1]
            break
    return nettoye.strip()


def demander_chemin(invite: str) -> str | None:
    """Demande un chemin existant. Renvoie None si l'on renonce."""
    while True:
        brut = _demander_ligne(f"{invite} (vide pour revenir)")
        if brut is None:
            return None
        chemin = _nettoyer_chemin(brut)
        if not chemin:
            return None
        if Path(chemin).expanduser().is_file():
            return chemin
        print(f"Fichier introuvable : {chemin}")


# --------------------------------------------------------------------------- #
# Navigateur de fichiers
# --------------------------------------------------------------------------- #

EXTENSIONS_IMAGE = (
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".ppm", ".tga",
)
EXTENSIONS_VIDEO = (
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".ts",
)
EXTENSIONS_POLICE = (".ttf", ".otf", ".ttc")

# Au-delà, la liste cesse d'être utile à parcourir ; on le signale plutôt que de
# la dérouler en entier.
_MAX_ENTREES = 500

# Dernier dossier visité, pour ne pas repartir de la racine à chaque ouverture.
_dernier_dossier: list[Path] = []

_PARENT = "parent"
_DOSSIER = "dossier"
_FICHIER = "fichier"
_DISQUE = "disque"
_ICI = "ici"


def _taille_lisible(chemin: Path) -> str:
    try:
        octets = float(chemin.stat().st_size)
    except OSError:
        return "?"
    for unite in ("o", "Ko", "Mo", "Go"):
        if octets < 1024.0 or unite == "Go":
            return f"{octets:.0f} {unite}" if unite == "o" else f"{octets:.1f} {unite}"
        octets /= 1024.0
    return "?"


def _disques() -> list[Path]:
    """Racines de disque disponibles. Vide ailleurs que sous Windows."""
    if sys.platform != "win32":
        return []
    from string import ascii_uppercase

    racines = []
    for lettre in ascii_uppercase:
        racine = Path(f"{lettre}:\\")
        try:
            if racine.exists():
                racines.append(racine)
        except OSError:
            continue
    return racines


def _contenu(
    dossier: Path, extensions: Sequence[str] | None
) -> tuple[list[Path], list[Path]]:
    """Sous-dossiers et fichiers retenus, triés sans tenir compte de la casse."""
    try:
        elements = list(dossier.iterdir())
    except OSError:
        return [], []

    dossiers: list[Path] = []
    fichiers: list[Path] = []
    for element in elements:
        try:
            if element.is_dir():
                dossiers.append(element)
            elif extensions is None or element.suffix.lower() in extensions:
                fichiers.append(element)
        except OSError:
            # Lien mort, ou point de montage inaccessible : on l'ignore.
            continue

    return (
        sorted(dossiers, key=lambda chemin: chemin.name.lower()),
        sorted(fichiers, key=lambda chemin: chemin.name.lower()),
    )


def _entrees_du_dossier(
    dossier: Path, extensions: Sequence[str] | None, *, dossier_seulement: bool
) -> list[Entree]:
    dossiers, fichiers = _contenu(dossier, extensions)
    if dossier_seulement:
        fichiers = []

    entrees: list[Entree] = []
    if dossier_seulement:
        entrees.append(Entree("[ choisir ce dossier ]", (_ICI, dossier)))
    if dossier.parent != dossier:
        entrees.append(Entree("..", (_PARENT, dossier.parent), "dossier parent"))

    tronque = False
    for chemin in dossiers:
        if len(entrees) >= _MAX_ENTREES:
            tronque = True
            break
        entrees.append(Entree(f"{chemin.name}/", (_DOSSIER, chemin), "dossier"))
    for chemin in fichiers:
        if len(entrees) >= _MAX_ENTREES:
            tronque = True
            break
        entrees.append(Entree(chemin.name, (_FICHIER, chemin), _taille_lisible(chemin)))

    if not dossiers and not fichiers:
        entrees.append(Entree("( rien à afficher ici )", (_DOSSIER, dossier)))
    if tronque:
        entrees.append(
            Entree(f"( liste limitée à {_MAX_ENTREES} entrées )", (_DOSSIER, dossier))
        )
    if _disques():
        entrees.append(Entree("[ changer de disque ]", (_DISQUE, None)))
    entrees.append(Entree("[ annuler ]", (QUITTER, None)))
    return entrees


def _depart(depart: Path | None) -> Path:
    """Dossier d'ouverture : celui demandé, le dernier visité, sinon le dossier courant."""
    for candidat in (depart, _dernier_dossier[0] if _dernier_dossier else None, Path.cwd()):
        if candidat is None:
            continue
        try:
            if candidat.is_dir():
                return candidat.resolve()
        except OSError:
            continue
    return Path.home()


def _memoriser(dossier: Path) -> None:
    _dernier_dossier.clear()
    _dernier_dossier.append(dossier)


def parcourir(
    titre: str,
    *,
    extensions: Sequence[str] | None = None,
    dossier_seulement: bool = False,
    depart: Path | None = None,
) -> Path | None:
    """Navigue dans l'arborescence et renvoie le chemin choisi, ou None.

    Les fichiers sont filtrés sur ``extensions`` pour que la liste ne montre que
    des médias exploitables ; les dossiers sont toujours affichés, faute de quoi
    on ne pourrait plus circuler.
    """
    dossier = _depart(depart)
    while True:
        entrees = _entrees_du_dossier(
            dossier, extensions, dossier_seulement=dossier_seulement
        )
        choix = selectionner(f"{titre}\n{dossier}", entrees)
        if choix is None:
            return None

        genre, cible = choix
        if genre == QUITTER:
            return None
        if genre == _ICI:
            _memoriser(dossier)
            return dossier
        if genre in (_PARENT, _DOSSIER):
            dossier = cible
        elif genre == _FICHIER:
            _memoriser(dossier)
            return cible
        elif genre == _DISQUE:
            racines = [Entree(str(racine), (_DOSSIER, racine)) for racine in _disques()]
            racines.append(Entree("[ annuler ]", (QUITTER, None)))
            disque = selectionner("Quel disque ?", racines)
            if disque is not None and disque[0] == _DOSSIER:
                dossier = disque[1]


def choisir_fichier(invite: str, extensions: Sequence[str] | None = None) -> str | None:
    """Choisit un fichier existant : navigateur sur un terminal, saisie sinon.

    Hors terminal, dérouler une arborescence en listes numérotées coûte plus
    cher que de coller un chemin : on demande donc le chemin directement.
    """
    if not interactif():
        return demander_chemin(invite)
    choisi = parcourir(invite, extensions=extensions)
    return None if choisi is None else str(choisi)


def noms_proposes(base: str, extensions: Sequence[str]) -> list[str]:
    """Noms de sortie proposés : un nom simple, puis un nom horodaté par extension.

    L'horodatage évite d'écraser un rendu précédent sans l'avoir voulu.
    """
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    simples = [f"{base}{extension}" for extension in extensions]
    dates = [f"{base}-{horodatage}{extension}" for extension in extensions]
    return simples + dates


def choisir_destination(invite: str, base: str, extensions: Sequence[str]) -> str | None:
    """Compose un chemin de sortie : un dossier parcouru, puis un nom proposé."""
    if not interactif():
        brut = _demander_ligne(f"{invite} (vide pour aucun)")
        return None if brut is None else _nettoyer_chemin(brut)

    dossier = parcourir(f"{invite} — où enregistrer ?", dossier_seulement=True)
    if dossier is None:
        return None
    entrees = [Entree(nom, nom) for nom in noms_proposes(base, extensions)]
    entrees.append(Entree("[ annuler ]", QUITTER))
    nom = selectionner(f"Nom du fichier\n{dossier}", entrees)
    if nom is None or nom == QUITTER:
        return None
    return str(dossier / str(nom))


# --------------------------------------------------------------------------- #
# Écran de réglages
# --------------------------------------------------------------------------- #

_LANCER = "lancer"
_ANNULER = "annuler"


def _ecran_reglages_numerote(titre: str, champs: Sequence[Champ]) -> bool:
    """Variante sans terminal : chaque champ est demandé une fois, dans l'ordre."""
    print(f"\n{titre} — réglages (Entrée pour garder la valeur affichée)")
    for champ in champs:
        if isinstance(champ, (Fichier, Sortie)):
            champ.ouvrir()
        elif isinstance(champ, Bascule):
            reponse = _demander_ligne(f"{champ.libelle} ? [o/N]")
            if reponse is None:
                return False
            champ.actif = reponse.strip().lower() in ("o", "oui", "y", "yes")
        else:
            possibles = [valeur or _DEFAUT for valeur in champ.valeurs]
            reponse = _demander_ligne(
                f"{champ.libelle} {possibles} [{champ.affichage()}]"
            )
            if reponse is None:
                return False
            choisi = reponse.strip()
            if choisi in champ.valeurs:
                champ.rang = champ.valeurs.index(choisi)
            elif choisi == _DEFAUT and "" in champ.valeurs:
                champ.rang = champ.valeurs.index("")
    return True


def ecran_reglages(titre: str, champs: Sequence[Champ]) -> bool:
    """Laisse ajuster les champs. Renvoie True s'il faut lancer le rendu."""
    if not interactif():
        return _ecran_reglages_numerote(titre, champs)

    style = _Style()
    zone = _Zone()
    actions = (_LANCER, _ANNULER)
    curseur = 0
    total = len(champs) + len(actions)
    largeur = max(len(champ.libelle) for champ in champs)

    while True:
        rangs = [
            f"{champ.libelle.ljust(largeur)}  {champ.affichage()}" for champ in champs
        ]
        rangs += ["Lancer le rendu", "Annuler"]
        apercu = " ".join(_argv_des_champs(champs))
        _dessiner_liste(
            zone, style, titre, rangs, curseur, [f"hachure … {apercu}", _INVITE_REGLAGES]
        )

        touche = lire_touche()
        if touche == "haut":
            curseur = (curseur - 1) % total
        elif touche == "bas":
            curseur = (curseur + 1) % total
        elif touche in ("echap", "interruption"):
            zone.effacer()
            return False
        elif curseur >= len(champs):
            if touche == "entree":
                zone.effacer()
                return actions[curseur - len(champs)] == _LANCER
        elif touche in (" ", "gauche", "droite"):
            champs[curseur].modifier(-1 if touche == "gauche" else 1)
        elif touche == "entree":
            zone.effacer()
            champs[curseur].ouvrir()


# --------------------------------------------------------------------------- #
# Jeux de réglages par commande
# --------------------------------------------------------------------------- #

_CHARSETS = tuple(sorted(CHARSETS))
_CHARSET_DEFAUT = _CHARSETS.index(DEFAULT_CHARSET)

# Le premier élément est vide : il laisse en place le défaut de la CLI.
_LARGEURS = ("", "60", "80", "100", "120", "160", "200", "240", "300", "500", "1000")
_HAUTEURS = ("", "15", "20", "25", "30", "40", "50", "60")
_FPS = ("", "10", "12", "15", "20", "24", "30", "60")
_DUREES = ("", "3", "5", "10", "15", "30", "60", "120")
_DEPARTS = ("", "5", "10", "15", "30", "60", "120", "300")
_LONGUEURS = ("", "8", "10", "12", "14", "16", "20")
_TAILLES = ("", "16", "24", "32", "48", "64")


def _champs_style(*, couleur: bool) -> list[Champ]:
    return [
        Bascule("--color", "Couleur", actif=couleur),
        Bascule("--edges", "Contours (--edges)", actif=True),
        Bascule("--auto-levels", "Niveaux automatiques", actif=True),
        Choix("--charset", "Jeu de caractères", _CHARSETS, _CHARSET_DEFAUT),
        Choix("--cells", "Géométrie de cellule", CELL_MODES),
        Bascule("--invert", "Inverser la rampe"),
    ]


def _champs_geometrie() -> list[Champ]:
    return [
        Choix("--width", "Largeur maximale", _LARGEURS),
        Choix("--height", "Hauteur maximale", _HAUTEURS),
        Choix("--fit", "Ajustement", FIT_MODES),
    ]


def champs_image(base: str = "rendu") -> list[Champ]:
    return [
        *_champs_geometrie(),
        *_champs_style(couleur=False),
        Sortie("--output", "Écrire dans un fichier texte", (".txt",), base),
    ]


def champs_video(base: str = "rendu") -> list[Champ]:
    return [
        *_champs_geometrie(),
        *_champs_style(couleur=True),
        Choix("--fps", "Images par seconde", _FPS),
        Bascule("--no-audio", "Couper le son"),
        Bascule("--loop", "Lire en boucle"),
        Choix("--start", "Départ en secondes", _DEPARTS),
        Choix("--duration", "Durée en secondes", _DUREES),
        Sortie("--record", "Enregistrer le rendu", (".mp4", ".gif"), base),
    ]


def champs_camera() -> list[Champ]:
    return [
        *_champs_geometrie(),
        *_champs_style(couleur=True),
        Choix("--fps", "Images par seconde", _FPS),
        Choix("--duration", "Durée en secondes", _DUREES),
        Sortie("--record", "Enregistrer le rendu", (".mp4", ".gif"), "camera"),
    ]


def champs_demo(base: str = "demo") -> list[Champ]:
    return [
        Choix("--width", "Largeur", _LARGEURS),
        Choix("--height", "Hauteur", _HAUTEURS),
        Choix("--fps", "Images par seconde", _FPS),
        Choix("--charset", "Jeu de caractères", _CHARSETS, _CHARSET_DEFAUT),
        Bascule("--invert", "Inverser la rampe"),
        Sortie("--record", "Enregistrer le rendu", (".gif", ".mp4"), base),
    ]


def champs_calibrate() -> list[Champ]:
    return [
        Fichier("--font", "Police à mesurer", EXTENSIONS_POLICE),
        Choix("--length", "Longueur de la rampe", _LONGUEURS),
        Choix("--size", "Taille de mesure en pixels", _TAILLES),
    ]


# --------------------------------------------------------------------------- #
# Écrans de composition
# --------------------------------------------------------------------------- #


def _composer_media(
    commande: str,
    invite: str,
    extensions: Sequence[str],
    champs: Callable[[str], list[Champ]],
) -> list[str] | None:
    chemin = choisir_fichier(invite, extensions)
    if chemin is None:
        return None
    # Le nom de la source sert de base aux noms d'enregistrement proposés.
    reglages = champs(Path(chemin).stem or "rendu")
    if not ecran_reglages(f"Réglages · {commande}", reglages):
        return None
    return [commande, chemin, *_argv_des_champs(reglages)]


def _composer_image() -> list[str] | None:
    return _composer_media("image", "Quelle image ?", EXTENSIONS_IMAGE, champs_image)


def _composer_video() -> list[str] | None:
    return _composer_media("video", "Quelle vidéo ?", EXTENSIONS_VIDEO, champs_video)


def _composer_camera() -> list[str] | None:
    from hachure.media.video import VideoRenderError, list_camera_devices

    entrees = [Entree("Caméra par défaut", "")]
    try:
        entrees += [Entree(nom, nom) for nom in list_camera_devices()]
    except VideoRenderError as exc:
        print(f"Liste des caméras indisponible : {exc}")
    entrees.append(Entree("[ annuler ]", QUITTER))

    choix = selectionner("Quelle caméra ?", entrees)
    if choix is None or choix == QUITTER:
        return None

    champs = champs_camera()
    if not ecran_reglages("Réglages · camera", champs):
        return None
    peripherique = ["--device", str(choix)] if choix else []
    return ["camera", *peripherique, *_argv_des_champs(champs)]


def _composer_demo() -> list[str] | None:
    entrees = [Entree(demo.name, demo.name, demo.description) for demo in DEMOS.values()]
    entrees.append(Entree("[ annuler ]", QUITTER))

    choix = selectionner("Quelle démo ?", entrees)
    if choix is None or choix == QUITTER:
        return None

    champs = champs_demo(str(choix))
    if not ecran_reglages(f"Réglages · demo {choix}", champs):
        return None
    return ["demo", str(choix), *_argv_des_champs(champs)]


def _composer_calibrate() -> list[str] | None:
    champs = champs_calibrate()
    if not ecran_reglages("Réglages · calibrate", champs):
        return None
    return ["calibrate", *_argv_des_champs(champs)]


# --------------------------------------------------------------------------- #
# Boucle principale
# --------------------------------------------------------------------------- #

# Chaque entrée compose une ligne de commande ; None signifie « revenir ici ».
_ACTIONS: tuple[tuple[str, str, Callable[[], list[str] | None]], ...] = (
    ("Image fixe", "convertir une photo en caractères", _composer_image),
    ("Vidéo", "lire un fichier vidéo", _composer_video),
    ("Caméra", "diffuser une caméra en direct", _composer_camera),
    ("Démo procédurale", "cube, sphère, tore, planète, trou noir", _composer_demo),
    ("Diagnostic", "dépendances et capacités du terminal", lambda: ["doctor"]),
    ("Moteurs disponibles", "ce que le projet sait rendre", lambda: ["list"]),
    ("Calibrer une rampe", "mesurer une police à chasse fixe", _composer_calibrate),
)

_BANNIERE = "hachure · rendu d'images, de vidéos et de 3D en caractères"


def executer_menu(lanceur: Callable[[Sequence[str]], int]) -> int:
    """Boucle sur le menu, en confiant chaque commande composée à ``lanceur``.

    Le code de sortie est celui de la dernière commande réellement lancée, pour
    qu'un échec reste visible après avoir quitté le menu.
    """
    entrees = [
        Entree(libelle, rang, detail)
        for rang, (libelle, detail, _) in enumerate(_ACTIONS)
    ]
    entrees.append(Entree("Quitter", QUITTER))

    code = 0
    while True:
        choix = selectionner(_BANNIERE, entrees)
        if choix is None or choix == QUITTER:
            return code

        try:
            argv = _ACTIONS[int(choix)][2]()
        except KeyboardInterrupt:
            print()
            continue
        if argv is None:
            continue

        print(f"\n$ hachure {' '.join(argv)}\n")
        try:
            code = lanceur(argv)
        except KeyboardInterrupt:
            print()
        if not interactif():
            return code
