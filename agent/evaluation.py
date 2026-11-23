"""Tests de positionnement et de passage de palier.

Correction automatique avec les banques d'exercices, sans l'agent (rapide, gratuit, reproductible).
- Passage : un exercice par leçon du palier de l'élève ; réussi à partir de SEUIL_PASSAGE (80 %).
- Positionnement : quelques questions par palier, en partant du premier ; on monte tant que
  l'élève réussit (au moins 2 sur 3), et on le place au premier palier qu'il ne réussit pas.
Dans les deux cas, le résultat est proposé au parent, qui le confirme.
"""

import json
import random
import sqlite3

from agent import parcours
from agent.db_utils import maintenant_iso
from agent.tools.corriger import evaluer
from agent.tools.donnees_exemple import EXERCICES, NOTIONS

QUESTIONS_POSITIONNEMENT = 3
REUSSITE_POSITIONNEMENT = 2


class TestImpossible(Exception):
    pass


def _exercice_pour(notion: str, hasard: random.Random) -> str:
    """Un exercice de difficulté moyenne de préférence (ni le plus facile ni le plus difficile)."""
    exercices = NOTIONS[notion]["exercices"]
    moyens = [e for e in exercices if e["difficulte"] == 2] or exercices
    return hasard.choice(moyens)["id"]


def _questions_passage(numero: int, hasard: random.Random) -> list[str]:
    return [_exercice_pour(n, hasard) for n in parcours.palier(numero)["notions"]]


def _questions_positionnement(numero: int, hasard: random.Random) -> list[str]:
    notions = parcours.palier(numero)["notions"]
    choisies = hasard.sample(notions, min(QUESTIONS_POSITIONNEMENT, len(notions)))
    return [_exercice_pour(n, hasard) for n in choisies]


def question_publique(exercice_id: str) -> dict:
    """Ce que l'élève voit : l'énoncé et les choix, jamais le corrigé."""
    from agent.tools._commun import choix_de_l_enonce

    _, ex = EXERCICES[exercice_id]
    return {"enonce": ex["enonce"], "choix": choix_de_l_enonce(ex["enonce"])}


def commencer(db: sqlite3.Connection, eleve_id: int, type_test: str, graine: int | None = None) -> int:
    hasard = random.Random(graine)
    (palier_actuel,) = db.execute("SELECT palier FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    if type_test == "passage":
        if palier_actuel is None:
            raise TestImpossible("Fais d'abord le test pour savoir où tu en es.")
        if palier_actuel >= parcours.DERNIER:
            raise TestImpossible("Tu es déjà au dernier palier du parcours.")
        etat = {"palier": palier_actuel, "questions": _questions_passage(palier_actuel, hasard), "reponses": []}
    elif type_test == "positionnement":
        etat = {"palier": 1, "questions": _questions_positionnement(1, hasard), "reponses": [], "reussis": [],
                "debut_bloc": 0}  # indice de la première question du palier en cours
    else:
        raise TestImpossible("Type de test inconnu.")
    # Un seul test en cours à la fois.
    db.execute(
        "UPDATE tests_palier SET statut = 'abandonne', fini_le = ? WHERE eleve_id = ? AND statut = 'en_cours'",
        (maintenant_iso(), eleve_id),
    )
    etat["graine"] = hasard.randrange(10**9)
    return db.execute(
        "INSERT INTO tests_palier (eleve_id, type, etat, statut, cree_le) VALUES (?, ?, ?, 'en_cours', ?)",
        (eleve_id, type_test, json.dumps(etat, ensure_ascii=False), maintenant_iso()),
    ).lastrowid


def charger(db: sqlite3.Connection, test_id: int, eleve_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, type, etat, statut, palier_propose, score FROM tests_palier WHERE id = ? AND eleve_id = ?",
        (test_id, eleve_id),
    ).fetchone()


def question_courante(test: sqlite3.Row) -> dict | None:
    etat = json.loads(test["etat"])
    i = len(etat["reponses"])
    if test["statut"] != "en_cours" or i >= len(etat["questions"]):
        return None
    return {**question_publique(etat["questions"][i]), "numero": i + 1, "palier": etat["palier"],
            "titre_palier": parcours.palier(etat["palier"])["titre"]}


def repondre(db: sqlite3.Connection, test: sqlite3.Row, reponse: str) -> dict:
    """Corrige une réponse et fait avancer le test. Renvoie le verdict et la suite (question ou résultat)."""
    etat = json.loads(test["etat"])
    i = len(etat["reponses"])
    if test["statut"] != "en_cours" or i >= len(etat["questions"]):
        raise TestImpossible("Ce test est terminé.")
    _, ex = EXERCICES[etat["questions"][i]]
    verdict, _ = evaluer(ex, reponse.strip()[:500])
    if verdict == "a_vocaliser":
        return {"verdict": "a_vocaliser", "question": question_courante(test)}  # on redemande, sans compter
    etat["reponses"].append({"exercice": ex["id"], "reponse": reponse, "juste": verdict == "juste"})

    statut, propose, score = "en_cours", None, None
    if len(etat["reponses"]) == len(etat["questions"]):
        if test["type"] == "passage":
            score = sum(r["juste"] for r in etat["reponses"]) / len(etat["reponses"])
            if score >= parcours.SEUIL_PASSAGE:
                statut, propose = "a_confirmer", etat["palier"] + 1
            else:
                statut = "echoue"
        else:
            bloc = etat["reponses"][etat["debut_bloc"]:]  # seulement les réponses du palier en cours
            reussi = sum(r["juste"] for r in bloc) >= min(REUSSITE_POSITIONNEMENT, len(bloc))
            if reussi and etat["palier"] < parcours.DERNIER:
                etat["reussis"].append(etat["palier"])
                etat["palier"] += 1
                etat["debut_bloc"] = len(etat["reponses"])
                hasard = random.Random(etat["graine"] + etat["palier"])
                etat["questions"] += _questions_positionnement(etat["palier"], hasard)
            else:
                if reussi:
                    etat["reussis"].append(etat["palier"])
                statut, propose = "a_confirmer", etat["palier"]
                score = sum(r["juste"] for r in etat["reponses"]) / len(etat["reponses"])

    db.execute(
        "UPDATE tests_palier SET etat = ?, statut = ?, palier_propose = ?, score = ?, fini_le = ? WHERE id = ?",
        (json.dumps(etat, ensure_ascii=False), statut, propose, score,
         None if statut == "en_cours" else maintenant_iso(), test["id"]),
    )
    test = db.execute("SELECT id, type, etat, statut, palier_propose, score FROM tests_palier WHERE id = ?",
                      (test["id"],)).fetchone()
    resultat = None
    if statut != "en_cours":
        resultat = {"statut": statut, "palier_propose": propose, "score": score,
                    "titre_palier": parcours.palier(propose)["titre"] if propose else None}
    return {"verdict": verdict, "question": question_courante(test), "resultat": resultat}


def confirmer(db: sqlite3.Connection, test_id: int, eleve_id: int, accepte: bool) -> int | None:
    """Le parent confirme (ou refuse) le résultat. Renvoie le nouveau palier si confirmé."""
    test = db.execute(
        "SELECT palier_propose, statut FROM tests_palier WHERE id = ? AND eleve_id = ?", (test_id, eleve_id)
    ).fetchone()
    if test is None or test["statut"] != "a_confirmer":
        raise TestImpossible("Aucun résultat à confirmer pour ce test.")
    db.execute(
        "UPDATE tests_palier SET statut = ? WHERE id = ?", ("confirme" if accepte else "refuse", test_id)
    )
    if accepte:
        db.execute("UPDATE eleves SET palier = ? WHERE id = ?", (test["palier_propose"], eleve_id))
        return test["palier_propose"]
    return None
