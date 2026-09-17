"""Registre des démonstrations procédurales intégrées."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hachure.i18n import T

from . import blackhole, cube, donut, planet, sphere

RenderFunction = Callable[[int, int, int, str], str]


@dataclass(frozen=True)
class Demo:
    """Une démonstration procédurale enregistrée.

    ``cle_description`` est une clé du catalogue, pas du texte : le registre est
    bâti à l'import, donc avant que la langue ne soit connue. La traduction se
    fait à l'affichage, via :meth:`description`.
    """

    name: str
    cle_description: str
    default_width: int
    height_ratio: float
    render: RenderFunction

    @property
    def description(self) -> str:
        return T(self.cle_description)


DEMOS = {
    demo.name: demo
    for demo in (
        Demo("cube", "demo.cube", 80, 0.44, cube.render_frame),
        Demo("sphere", "demo.sphere", 80, 0.44, sphere.render_frame),
        Demo("donut", "demo.donut", 80, 0.44, donut.render_frame),
        Demo("planet", "demo.planet", 90, 0.42, planet.render_frame),
        Demo("blackhole", "demo.blackhole", 100, 0.42, blackhole.render_frame),
    )
}


def get_demo(name: str) -> Demo:
    try:
        return DEMOS[name]
    except KeyError as exc:
        raise ValueError(T("erreur.demo_inconnue", nom=name)) from exc
