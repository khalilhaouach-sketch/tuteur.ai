"""Parcours unique en paliers (du CP à la 1AC), chargé depuis agent/parcours.yaml.

Chaque palier a un identifiant fixe (« 1ac-1 »...), enregistré en base pour chaque élève : on peut
ainsi insérer de nouveaux paliers sans changer la position des enfants. Le numéro d'un palier
(1, 2, 3...) vient de sa place dans le fichier et sert à l'affichage et aux comparaisons.
"""

import sqlite3
from pathlib import Path

import yaml

from agent.tools.donnees_exemple import NOTIONS

_DONNEES = yaml.safe_load(Path(__file__).with_name("parcours.yaml").read_text(encoding="utf-8"))
SEUIL_PASSAGE = _DONNEES["seuil_passage"]
PALIERS: list[dict] = [{**p, "numero": i} for i, p in enumerate(_DONNEES["paliers"], 1)]
DERNIER = len(PALIERS)
_NUMERO_DE = {p["id"]: p["numero"] for p in PALIERS}
assert len(_NUMERO_DE) == DERNIER, "identifiant de palier en double"

# Ordre des paliers dans la première version du parcours (bases créées avant les identifiants fixes).
ANCIENS_IDS = ["lettres-1", "lettres-2", "lettres-3", "transition-1", "transition-2", "transition-3",
               "1ac-1", "1ac-2", "1ac-3", "1ac-4"]

_PALIER_DE: dict[str, int] = {}
for _p in PALIERS:
    for _n in _p["notions"]:
        assert _n in NOTIONS, f"notion inconnue dans parcours.yaml : {_n}"
        assert _n not in _PALIER_DE, f"notion dans deux paliers : {_n}"
        _PALIER_DE[_n] = _p["numero"]


def palier(numero: int) -> dict:
    return PALIERS[numero - 1]


def numero_de(palier_id: str | None) -> int | None:
    return _NUMERO_DE.get(palier_id) if palier_id else None


def id_de(numero: int | None) -> str | None:
    return palier(numero)["id"] if numero else None


def palier_de(notion: str) -> int | None:
    return _PALIER_DE.get(notion)


def notions_accessibles(numero: int) -> list[str]:
    """Notions du palier de l'élève et des paliers précédents (pour réviser), dans l'ordre du parcours."""
    return [n for p in PALIERS[:numero] for n in p["notions"]]


def palier_eleve(db: sqlite3.Connection, eleve_id: int) -> int | None:
    """Numéro du palier actuel de l'élève (None : pas encore positionné)."""
    ligne = db.execute("SELECT palier FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    return numero_de(ligne[0]) if ligne else None


def fixer_palier(db: sqlite3.Connection, eleve_id: int, numero: int) -> None:
    db.execute("UPDATE eleves SET palier = ? WHERE id = ?", (id_de(numero), eleve_id))


def page_markdown() -> str:
    """Vue d'ensemble lisible du parcours (PARCOURS.md)."""
    lignes = ["# Parcours d'arabe en paliers (du CP à la 1AC)", "",
              "> Généré à partir de agent/parcours.yaml (`python3 -m agent.parcours`). Un enfant avance en réussissant",
              f"> le test de passage d'un palier ({int(SEUIL_PASSAGE * 100)} %), confirmé par le parent.", ""]
    for p in PALIERS:
        lignes += [f"## Palier {p['numero']} : {p['titre']}", "", p["description"], "",
                   "Leçons : " + "، ".join(p["notions"]) + ".", ""]
    return "\n".join(lignes)


if __name__ == "__main__":
    Path(__file__).resolve().parents[1].joinpath("PARCOURS.md").write_text(page_markdown(), encoding="utf-8")
    print(f"PARCOURS.md régénéré ({DERNIER} paliers).")
