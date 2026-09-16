"""Registre des démonstrations procédurales intégrées."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import blackhole, cube, donut, planet, sphere

RenderFunction = Callable[[int, int, int, str], str]


@dataclass(frozen=True)
class Demo:
    name: str
    description: str
    default_width: int
    height_ratio: float
    render: RenderFunction


DEMOS = {
    demo.name: demo
    for demo in (
        Demo("cube", "Cube plein en rotation, avec éclairage et tampon de profondeur", 80, 0.44, cube.render_frame),
        Demo("sphere", "Sphère en rotation, ombrée mathématiquement", 80, 0.44, sphere.render_frame),
        Demo("donut", "Tore paramétrique, avec éclairage et tampon de profondeur", 80, 0.44, donut.render_frame),
        Demo("planet", "Planète procédurale, avec relief et halo atmosphérique", 90, 0.42, planet.render_frame),
        Demo("blackhole", "Disque d'accrétion stylisé, étoiles et anneau de photons", 100, 0.42, blackhole.render_frame),
    )
}


def get_demo(name: str) -> Demo:
    try:
        return DEMOS[name]
    except KeyError as exc:
        raise ValueError(f"Démo inconnue : {name}") from exc
