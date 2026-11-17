"""Fonctions partagées par les outils."""

import re
import sqlite3

from agent.tools.donnees_exemple import EXERCICES, NOTIONS

NOMS_NOTIONS = sorted(NOTIONS)


class ErreurOutil(Exception):
    """Erreur renvoyée au modèle (is_error) au lieu de faire échouer la séance."""


# Voyelles brèves, tanwin, chadda, soukoun, alif suscrit et tatweel.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")
_PONCTUATION = re.compile(r"[.,;:!?،؛؟«»\"'()\[\]\-]")
_ALIF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا"})


def normaliser(texte: str, tolerer_hamza: bool = True) -> str:
    """Compare les réponses sans tenir compte des voyelles, de la ponctuation ni des espaces."""
    texte = _TASHKEEL.sub("", texte)
    texte = _PONCTUATION.sub(" ", texte)
    if tolerer_hamza:
        texte = texte.translate(_ALIF)
    return " ".join(texte.split())


def notion_id(db: sqlite3.Connection, intitule: str) -> int:
    niveau = NOTIONS[intitule]["niveau"]
    db.execute(
        "INSERT OR IGNORE INTO notions (matiere, niveau, intitule, reference_programme)"
        " VALUES ('arabe', ?, ?, ?)",
        (niveau, intitule, "exemple"),
    )
    (nid,) = db.execute(
        "SELECT id FROM notions WHERE niveau = ? AND intitule = ?", (niveau, intitule)
    ).fetchone()
    return nid


def exercice(exercice_id: str):
    if exercice_id not in EXERCICES:
        raise ErreurOutil(f"exercice inconnu : {exercice_id}")
    return EXERCICES[exercice_id]


def notion_valide(intitule: str) -> str:
    if intitule not in NOTIONS:
        raise ErreurOutil(f"notion inconnue : {intitule}. Notions disponibles : {', '.join(NOMS_NOTIONS)}")
    return intitule


def schema(proprietes: dict, requis: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": proprietes,
        "required": requis if requis is not None else list(proprietes),
        "additionalProperties": False,
    }
