"""Fonctions partagées par les outils."""

import re
import sqlite3

from agent.tools.donnees_exemple import EXERCICES, NOTIONS

NOMS_NOTIONS = sorted(NOTIONS)


class ErreurOutil(Exception):
    """Erreur renvoyée au modèle (is_error) au lieu de faire échouer la séance."""


# Voyelles brèves, tanwin, chadda, soukoun et alif suscrit (« ـٰ »).
_DIACRITIQUES = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0670")
SOUKOUN = "\u0652"
CHADDA = "\u0651"
KASRA = "\u0650"
_TASHKEEL = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_PONCTUATION = re.compile(r"[.,;:!?،؛؟«»\"'()\[\]\-]")
_ALIF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا"})


def normaliser(texte: str, tolerer_hamza: bool = True) -> str:
    """Squelette du texte : sans voyelles, ponctuation ni espaces superflus.
    Sert à reconnaître les lettres (et à repérer le corrigé dans les evals), pas à corriger."""
    texte = _TASHKEEL.sub("", texte)
    texte = _PONCTUATION.sub(" ", texte)
    if tolerer_hamza:
        texte = texte.translate(_ALIF)
    return " ".join(texte.split())


def decomposer(texte: str, tolerer_hamza: bool = True) -> list[tuple[str, frozenset]]:
    """Liste de (lettre, voyelles portées par la lettre). Les espaces comptent comme une lettre sans voyelle."""
    texte = _PONCTUATION.sub(" ", texte.replace("\u0640", ""))
    if tolerer_hamza:
        texte = texte.translate(_ALIF)
    texte = " ".join(texte.split())
    sortie: list[tuple[str, set]] = []
    for c in texte:
        if c in _DIACRITIQUES:
            if sortie:
                sortie[-1][1].add(c)
        else:
            sortie.append((c, set()))
    return [(l, frozenset(v)) for l, v in sortie]


def _facultatives(lettres: list[tuple[str, frozenset]], i: int) -> frozenset:
    """Voyelles qu'on peut omettre : le soukoun, et la voyelle de l'alif de liaison en début de mot."""
    l, v = lettres[i]
    debut_de_mot = i == 0 or lettres[i - 1][0] == " "
    if l == "ا" and debut_de_mot:
        return v
    return v & {SOUKOUN}


def comparer(reponse: str, attendue: str, voyelles_obligatoires: bool, tolerer_hamza: bool = True) -> str:
    """Compare deux réponses lettre par lettre, voyelles comprises.

    Renvoie « juste », « lettres » (lettres différentes), « voyelles » (une voyelle écrite est fausse)
    ou « a_vocaliser » (voyelles manquantes alors qu'elles sont exigées).
    Une voyelle écrite par l'élève est toujours vérifiée ; les voyelles absentes ne sont acceptées
    que si l'exercice ne les exige pas (le soukoun et la voyelle de l'alif de liaison restent facultatifs).
    """
    r, a = decomposer(reponse, tolerer_hamza), decomposer(attendue, tolerer_hamza)
    if [l for l, _ in r] != [l for l, _ in a]:
        return "lettres"
    manquantes = False
    for i, ((_, vr), (_, va)) in enumerate(zip(r, a)):
        if not vr <= va:
            return "voyelles"  # une voyelle écrite par l'élève n'est pas la bonne
        oubliees = (va - _facultatives(a, i)) - vr
        if vr and CHADDA in oubliees:
            return "voyelles"  # lettre vocalisée mais chadda oubliée : c'est une erreur, pas un oubli de شكل
        if oubliees:
            manquantes = True
    if manquantes and voyelles_obligatoires:
        return "a_vocaliser"
    return "juste"


def a_des_voyelles(texte: str) -> bool:
    return any(c in _DIACRITIQUES for c in texte)


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
