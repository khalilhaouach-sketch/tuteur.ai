"""Séance sans IA : le serveur mène seul la séance à partir des contenus stockés.

Présentation de la leçon (docs/cours/), exercice et boutons (banques YAML), correction (outil corriger, qui
enregistre la progression et planifie la révision), indice après la 1re erreur, explication après la 2e,
félicitations tirées d'une banque de phrases, passage à la leçon suivante du palier, récapitulatif de fin.

L'IA (agent/core.py) n'est appelée que si l'élève écrit un message libre, ou touche « لَمْ أَفْهَمْ »
alors que l'explication stockée a déjà été donnée. Les échanges sont ajoutés au même journal que les séances
avec l'IA (format des messages de l'API) : le parent les lit de la même façon.
"""

import json
import random
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from agent.tools import Contexte, corriger, generer_exercice
from agent.tools._commun import choix_de_l_enonce, normaliser
from agent.tools.donnees_exemple import EXERCICES

PAS_COMPRIS = "لَمْ أَفْهَمْ"
OUVERTURE = "[L'élève ouvre une nouvelle séance.]"
DOSSIER_COURS = Path(__file__).resolve().parent.parent / "docs" / "cours"

BRAVO = ["أَحْسَنْتَ! 🌟", "مُمْتَازٌ! 👏", "رَائِعٌ! ⭐", "جَوَابٌ صَحِيحٌ! 🎉", "أَنْتَ بَطَلٌ! 💪", "بَارَكَ اللَّهُ فِيكَ! 🌟"]
ENCORE = ["لَيْسَ تَمَامًا، حَاوِلْ مَرَّةً أُخْرَى.", "اِقْتَرَبْتَ! حَاوِلْ مَرَّةً أُخْرَى.", "لَا بَأْسَ، فَكِّرْ قَلِيلًا وَحَاوِلْ."]
APRES_ECHEC = "لَا بَأْسَ، نَتَعَلَّمُ مِنَ الخَطَإِ."
CONSIGNE_QUESTION = (
    "Séance sans IA : tu interviens seulement pour répondre au dernier message de l'élève, à propos de "
    "l'exercice en cours : « {enonce} ». Réponds en deux ou trois phrases très simples, en arabe vocalisé, "
    "sans donner la réponse, puis invite-le à toucher un bouton. N'appelle aucun outil."
)


# --- Contenus stockés ------------------------------------------------------------


@lru_cache
def _sections_de_cours() -> list[tuple[str, str]]:
    """(titre normalisé, texte) de chaque section des cours, cours de transition en premier."""
    sections = []
    fichiers = sorted(DOSSIER_COURS.glob("*.md"), key=lambda f: (not f.name.startswith("parcours_"), f.name))
    for fichier in fichiers:
        for bloc in re.split(r"^## ", fichier.read_text(encoding="utf-8"), flags=re.M)[1:]:
            titre, _, corps = bloc.partition("\n")
            sections.append((normaliser(titre), corps.strip()))
    return sections


def presentation(notion: str) -> str:
    """Résumé de la leçon tiré de docs/cours/ (sans la ligne de jeu, remplacée par les exercices)."""
    cle = normaliser(notion)
    for titre, corps in _sections_de_cours():
        if titre.startswith(cle) or cle in titre:
            lignes = [re.sub(r"^- ", "• ", l) for l in corps.splitlines() if l.strip() and "لُعْبَةٌ" not in l]
            return "\n".join(lignes[:8])
    return ""


# --- État de la séance (colonnes de la table seances) ----------------------------


def _etat(db: sqlite3.Connection, seance_id: int) -> sqlite3.Row:
    return db.execute(
        "SELECT s.id, s.eleve_id, s.journal, s.exercice_en_cours, s.aide_donnee, s.exercices_faits,"
        " s.objectif, e.prenom FROM seances s JOIN eleves e ON e.id = s.eleve_id WHERE s.id = ?",
        (seance_id,),
    ).fetchone()


def _ajouter(db, seance_id: int, eleve: str | None, tuteur: str) -> None:
    (journal,) = db.execute("SELECT journal FROM seances WHERE id = ?", (seance_id,)).fetchone()
    messages = json.loads(journal)
    if eleve is not None:
        messages.append({"role": "user", "content": eleve})
    messages.append({"role": "assistant", "content": [{"type": "text", "text": tuteur}]})
    db.execute("UPDATE seances SET journal = ? WHERE id = ?", (json.dumps(messages, ensure_ascii=False), seance_id))


def choix_courants(db, seance_id: int) -> list[str]:
    (ex_id,) = db.execute("SELECT exercice_en_cours FROM seances WHERE id = ?", (seance_id,)).fetchone()
    return choix_de_l_enonce(EXERCICES[ex_id][1]["enonce"]) if ex_id else []


# --- Déroulement -------------------------------------------------------------------


def _proposer(ctx: Contexte, notion_precedente: str | None) -> tuple[str, str | None]:
    """Texte de l'exercice suivant (avec la présentation si la leçon change) et son identifiant."""
    suivant = generer_exercice.exercice_suivant(ctx)
    if "exercice_id" not in suivant:
        if suivant.get("palier_termine"):
            return ("🏆 أَتْمَمْتَ كُلَّ دُرُوسِ هَذِهِ المَرْحَلَةِ! اُطْلُبْ مِنْ وَالِدَيْكَ أَنْ تَجْتَازَ "
                    "اخْتِبَارَ المُرُورِ (زِرُّ « Test de passage »)."), None
        return "أَنْهَيْتَ كُلَّ التَّمَارِينِ الجَدِيدَةِ لِهَذَا اليَوْمِ. أَحْسَنْتَ!", None
    parties = []
    if suivant["notion"] != notion_precedente:
        parties.append(f"📘 دَرْسٌ جَدِيدٌ: {suivant['notion']}")
        resume = presentation(suivant["notion"])
        if resume:
            parties.append(resume)
    parties.append(suivant["enonce"])
    return "\n\n".join(parties), suivant["exercice_id"]


def ouvrir(db, eleve_id: int, seance_id: int, objectif: int) -> str:
    ctx = Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil="P1")
    (prenom,) = db.execute("SELECT prenom FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    texte, ex_id = _proposer(ctx, None)
    message = f"مَرْحَبًا يَا {prenom}! 👋 هَيَّا نَتَعَلَّمُ.\n\n{texte}"
    db.execute("UPDATE seances SET mode = 'local', objectif = ?, exercice_en_cours = ?, aide_donnee = 0,"
               " exercices_faits = 0 WHERE id = ?", (objectif, ex_id, seance_id))
    _ajouter(db, seance_id, OUVERTURE, message)
    return message


def repondre(db, eleve_id: int, seance_id: int, texte: str, tuteur=None) -> dict:
    """Réponse à un message de l'élève. Renvoie {"reponse", "terminee"}."""
    etat = _etat(db, seance_id)
    ex_id = etat["exercice_en_cours"]
    if ex_id is None:  # plus d'exercice : la séance est finie
        return {"reponse": recapitulatif(db, eleve_id, seance_id), "terminee": True}
    notion, ex = EXERCICES[ex_id]
    choix = choix_de_l_enonce(ex["enonce"])
    ctx = Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil="P1")

    if texte == PAS_COMPRIS:
        if etat["aide_donnee"] == 0:
            message = f"{ex['indice']}\n\n{ex['enonce']}"
            db.execute("UPDATE seances SET aide_donnee = 1 WHERE id = ?", (seance_id,))
        elif etat["aide_donnee"] == 1:
            message = f"{ex['explication']}\n\n{ex['enonce']}"
            db.execute("UPDATE seances SET aide_donnee = 2 WHERE id = ?", (seance_id,))
        else:
            return _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, tuteur)
        _ajouter(db, seance_id, texte, message)
        return {"reponse": message, "terminee": False}

    if choix and texte not in choix:
        return _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, tuteur)

    resultat = corriger.executer(ctx, {"exercice_id": ex_id, "reponse": texte})
    if resultat["verdict"] == "a_vocaliser":
        message = f"{resultat['consigne']}\n\n{ex['enonce']}"
    elif not resultat["exercice_termine"]:
        message = f"{random.choice(ENCORE)}\n{resultat['indice']}\n\n{ex['enonce']}"
        db.execute("UPDATE seances SET aide_donnee = MAX(aide_donnee, 1) WHERE id = ?", (seance_id,))
    else:
        if resultat["verdict"] == "juste":
            debut = random.choice(BRAVO)
        else:
            debut = f"{APRES_ECHEC}\n{resultat['explication']}\nالجَوَابُ الصَّحِيحُ: «{resultat['bonne_reponse']}»."
        faits = etat["exercices_faits"] + 1
        if faits >= etat["objectif"]:
            db.execute("UPDATE seances SET exercices_faits = ?, exercice_en_cours = NULL WHERE id = ?", (faits, seance_id))
            fin = recapitulatif(db, eleve_id, seance_id)
            _ajouter(db, seance_id, texte, f"{debut}\n\n{fin}")
            return {"reponse": f"{debut}\n\n{fin}", "terminee": True}
        suite, nouvel_ex = _proposer(ctx, notion)
        db.execute("UPDATE seances SET exercices_faits = ?, exercice_en_cours = ?, aide_donnee = 0 WHERE id = ?",
                   (faits, nouvel_ex, seance_id))
        message = f"{debut}\n\n{suite}"
        if nouvel_ex is None:
            _ajouter(db, seance_id, texte, message)
            return {"reponse": message, "terminee": True}
    _ajouter(db, seance_id, texte, message)
    return {"reponse": message, "terminee": False}


def _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, tuteur) -> dict:
    """Seul cas payant : un message libre de l'élève (ou une incompréhension après l'explication)."""
    if tuteur is None:
        message = f"{ex['explication']}\n\n{ex['enonce']}"
        _ajouter(db, seance_id, texte, message)
        return {"reponse": message, "terminee": False}
    from agent.core import TuteurIndisponible

    try:
        reponse = tuteur.repondre(db, eleve_id, seance_id, texte, boutons=(PAS_COMPRIS,),
                                  consigne=CONSIGNE_QUESTION.format(enonce=ex["enonce"]), outils=False)
    except TuteurIndisponible:  # sans IA joignable, on redonne l'explication stockée
        reponse = ex["explication"]
        _ajouter(db, seance_id, texte, f"{reponse}\n\n{ex['enonce']}")
    message = f"{reponse}\n\n{ex['enonce']}"
    return {"reponse": message, "terminee": False}


def recapitulatif(db, eleve_id: int, seance_id: int) -> str:
    etat = _etat(db, seance_id)
    lecons = [r["intitule"] for r in db.execute(
        "SELECT n.intitule FROM tentatives t JOIN notions n ON n.id = t.notion_id WHERE t.seance_id = ?"
        " GROUP BY n.intitule ORDER BY MIN(t.id)", (seance_id,))]
    (reussis,) = db.execute(
        "SELECT COUNT(DISTINCT exercice) FROM tentatives WHERE seance_id = ? AND verdict = 'juste'", (seance_id,)
    ).fetchone()
    if not lecons:
        return f"إِلَى اللِّقَاءِ يَا {etat['prenom']}! 👋"
    return (f"🎉 أَحْسَنْتَ يَا {etat['prenom']}! تَمَرَّنْتَ اليَوْمَ عَلَى: {'، '.join(lecons)}.\n"
            f"الإِجَابَاتُ الصَّحِيحَةُ: {reussis} / {etat['exercices_faits']}. إِلَى اللِّقَاءِ!")


def conclure(db, eleve_id: int, seance_id: int) -> str:
    message = recapitulatif(db, eleve_id, seance_id)
    db.execute("UPDATE seances SET exercice_en_cours = NULL WHERE id = ?", (seance_id,))
    _ajouter(db, seance_id, "[L'élève termine la séance.]", message)
    return message
