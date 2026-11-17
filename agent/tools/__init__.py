"""Les six outils de l'agent tuteur. Ce sont les SEULS outils auxquels l'agent a accès.

L'élève concerné n'est jamais choisi par le modèle : il vient de la séance (Contexte).
"""

from dataclasses import dataclass
import sqlite3

from agent.tools._commun import ErreurOutil
from agent.tools import (
    corriger,
    enregistrer_progression,
    generer_exercice,
    lire_programme,
    planifier_revision,
    rapport_parent,
)


@dataclass
class Contexte:
    db: sqlite3.Connection
    eleve_id: int
    seance_id: int | None
    profil: str


MODULES = [
    lire_programme,
    generer_exercice,
    corriger,
    enregistrer_progression,
    planifier_revision,
    rapport_parent,
]
OUTILS = {m.DEFINITION["name"]: m for m in MODULES}
DEFINITIONS = [m.DEFINITION for m in MODULES]


def executer(ctx: Contexte, nom: str, entree: dict) -> dict:
    if nom not in OUTILS:
        raise ErreurOutil(f"outil inconnu : {nom}")
    return OUTILS[nom].executer(ctx, entree)
