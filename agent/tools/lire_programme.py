"""Retrouve le passage du programme sur une notion."""

from agent.tools._commun import NOMS_NOTIONS, notion_valide, schema
from agent.tools.donnees_exemple import NOTIONS, REFERENCE

DEFINITION = {
    "name": "lire_programme",
    "description": (
        "Renvoie l'extrait du programme officiel et des cours sur une notion d'arabe, avec sa référence. "
        "À appeler avant d'expliquer une notion : n'explique que ce qui figure dans l'extrait."
    ),
    "strict": True,
    "input_schema": schema({"notion": {"type": "string", "enum": NOMS_NOTIONS}}),
}


def executer(ctx, entree: dict) -> dict:
    notion = notion_valide(entree["notion"])
    donnees = NOTIONS[notion]
    return {
        "notion": notion,
        "extrait": donnees["extrait"],
        "exemples": donnees["exemples"],
        "reference": REFERENCE,
    }
