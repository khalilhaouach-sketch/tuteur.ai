"""Parcours unique en paliers (du CP à la 1AC), chargé depuis agent/parcours.yaml."""

from pathlib import Path

import yaml

from agent.tools.donnees_exemple import NOTIONS

_DONNEES = yaml.safe_load(Path(__file__).with_name("parcours.yaml").read_text(encoding="utf-8"))
SEUIL_PASSAGE = _DONNEES["seuil_passage"]
PALIERS: list[dict] = _DONNEES["paliers"]
DERNIER = len(PALIERS)

_PALIER_DE: dict[str, int] = {}
for _p in PALIERS:
    for _n in _p["notions"]:
        assert _n in NOTIONS, f"notion inconnue dans parcours.yaml : {_n}"
        assert _n not in _PALIER_DE, f"notion dans deux paliers : {_n}"
        _PALIER_DE[_n] = _p["numero"]


def palier(numero: int) -> dict:
    return PALIERS[numero - 1]


def palier_de(notion: str) -> int | None:
    return _PALIER_DE.get(notion)


def notions_accessibles(numero: int) -> list[str]:
    """Notions du palier de l'élève et des paliers précédents (pour réviser), dans l'ordre du parcours."""
    return [n for p in PALIERS[:numero] for n in p["notions"]]
