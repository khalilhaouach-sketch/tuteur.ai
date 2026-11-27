"""Séance sans IA : le serveur mène seul la séance à partir des contenus stockés.

Présentation de la leçon (docs/cours/), exercice et boutons (banques YAML), correction (outil corriger, qui
enregistre la progression et planifie la révision), indice après la 1re erreur, explication après la 2e,
félicitations tirées d'une banque de phrases, passage à la leçon suivante du palier, récapitulatif de fin.

L'IA (agent/core.py) n'est appelée que si l'élève pose une question (bouton « Poser une question » des
grands), touche « لَمْ أَفْهَمْ » alors que l'explication stockée a déjà été donnée, ou écrit un texte qui
déclenche le contrôle de sécurité. Ses réponses sont gardées (table reponses_ia) et réutilisées pour la
même question sur le même exercice. Les échanges sont ajoutés au même journal que les séances
avec l'IA (format des messages de l'API) : le parent les lit de la même façon.
"""

import json
import random
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from agent.db_utils import maintenant_iso
from agent.safety import detresse, filtres
from agent.tools import Contexte, corriger, generer_exercice
from agent.tools._commun import choix_de_l_enonce, normaliser
from agent.tools.donnees_exemple import EXERCICES

PAS_COMPRIS = "لَمْ أَفْهَمْ"
SUIVANT = "فَهِمْتُ، التَّالِي ←"
OUVERTURE = "[L'élève ouvre une nouvelle séance.]"
DOSSIER_COURS = Path(__file__).resolve().parent.parent / "docs" / "cours"

BRAVO = ["أَحْسَنْتَ! 🌟", "مُمْتَازٌ! 👏", "رَائِعٌ! ⭐", "جَوَابٌ صَحِيحٌ! 🎉", "أَنْتَ بَطَلٌ! 💪", "بَارَكَ اللَّهُ فِيكَ! 🌟"]
ENCORE = ["لَيْسَ تَمَامًا، حَاوِلْ مَرَّةً أُخْرَى.", "اِقْتَرَبْتَ! حَاوِلْ مَرَّةً أُخْرَى.", "لَا بَأْسَ، فَكِّرْ قَلِيلًا وَحَاوِلْ."]
APRES_ECHEC = "لَا بَأْسَ، نَتَعَلَّمُ مِنَ الخَطَإِ."
CONSIGNE_QUESTION = (
    "Séance sans IA : tu interviens seulement pour répondre au dernier message de l'élève, à propos de "
    "l'exercice en cours : « {enonce} ». Réponds en deux ou trois phrases très simples, en arabe vocalisé, "
    "sans donner la réponse, puis invite-le à répondre à l'exercice. N'appelle aucun outil. "
    "N'écris pas le prénom de l'élève : cette réponse pourra être réutilisée pour la même question."
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


def _resume(corps: str) -> str:
    lignes = [re.sub(r"^- ", "• ", l) for l in corps.splitlines() if l.strip() and "لُعْبَةٌ" not in l]
    return "\n".join(lignes[:8])


def _section(notion: str) -> str | None:
    """Section de cours d'une leçon : titre identique, sinon titre qui commence par le nom de la leçon,
    sinon titre qui le contient comme mots entiers (« إن وأخواتها » ne doit pas trouver « كان وأخواتها »)."""
    cle = normaliser(notion)
    sections = _sections_de_cours()
    for test in (lambda t: t == cle,
                 lambda t: t.startswith(cle + " ") or t.startswith(cle),
                 lambda t: f" {cle} " in f" {t} "):
        for titre, corps in sections:
            if test(titre):
                return corps
    return None


def etapes(notion: str) -> list[str]:
    """Leçon découpée en petites étapes (lignes « --- » dans la section de docs/cours/) ; [] si non découpée."""
    corps = _section(notion)
    if not corps or not re.search(r"^---\s*$", corps, re.M):
        return []
    return [
        "\n".join(re.sub(r"^- ", "• ", l) for l in bloc.strip().splitlines() if l.strip())
        for bloc in re.split(r"^---\s*$", corps, flags=re.M) if bloc.strip()
    ]


def presentation(notion: str, db=None) -> str:
    """Résumé de la leçon tiré de docs/cours/ (sans la ligne de jeu, remplacée par les exercices) :
    la section qui porte le nom de la leçon, sinon le passage de cours le plus proche (recherche du RAG)."""
    corps = _section(notion)
    if corps:
        return _resume(corps)
    if db is not None:
        from rag.search import chercher

        for passage in chercher(db, notion, limite=5):
            if "cours/" in passage["reference"]:
                return _resume(passage["texte"])
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
    ex_id, etape = db.execute("SELECT exercice_en_cours, etape_cours FROM seances WHERE id = ?", (seance_id,)).fetchone()
    if etape is not None:
        return [SUIVANT]
    return choix_de_l_enonce(EXERCICES[ex_id][1]["enonce"]) if ex_id else []


# --- Déroulement -------------------------------------------------------------------


def _proposer(ctx: Contexte, notion_precedente: str | None) -> tuple[str, str | None]:
    """Texte de l'exercice suivant (avec la présentation si la leçon change) et son identifiant.
    Leçon découpée en étapes : on montre la 1re étape ; l'exercice viendra après la dernière."""
    suivant = generer_exercice.exercice_suivant(ctx)
    if "exercice_id" not in suivant:
        if suivant.get("palier_termine"):
            return ("🏆 أَتْمَمْتَ كُلَّ دُرُوسِ هَذِهِ المَرْحَلَةِ! اُطْلُبْ مِنْ وَالِدَيْكَ أَنْ تَجْتَازَ "
                    "اخْتِبَارَ المُرُورِ (زِرُّ « Test de passage »)."), None
        return "أَنْهَيْتَ كُلَّ التَّمَارِينِ الجَدِيدَةِ لِهَذَا اليَوْمِ. أَحْسَنْتَ!", None
    parties = []
    ctx.db.execute("UPDATE seances SET etape_cours = NULL WHERE id = ?", (ctx.seance_id,))
    if suivant["notion"] != notion_precedente:
        parties.append(f"📘 دَرْسٌ جَدِيدٌ: {suivant['notion']}")
        decoupee = etapes(suivant["notion"])
        if len(decoupee) > 1:
            ctx.db.execute("UPDATE seances SET etape_cours = 0 WHERE id = ?", (ctx.seance_id,))
            parties.append(_etape(decoupee, 0))
            return "\n\n".join(parties), suivant["exercice_id"]
        resume = presentation(suivant["notion"], ctx.db)
        if resume:
            parties.append(resume)
    parties.append(suivant["enonce"])
    return "\n\n".join(parties), suivant["exercice_id"]


def _etape(decoupee: list[str], n: int) -> str:
    return f"({n + 1}/{len(decoupee)})\n{decoupee[n]}"


def _contexte(db, eleve_id: int, seance_id: int) -> Contexte:
    (profil,) = db.execute("SELECT profil FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    return Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil=profil)


def ouvrir(db, eleve_id: int, seance_id: int, objectif: int) -> str:
    ctx = _contexte(db, eleve_id, seance_id)
    (prenom,) = db.execute("SELECT prenom FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    texte, ex_id = _proposer(ctx, None)
    message = f"مَرْحَبًا يَا {prenom}! 👋 هَيَّا نَتَعَلَّمُ.\n\n{texte}"
    db.execute("UPDATE seances SET mode = 'local', objectif = ?, exercice_en_cours = ?, aide_donnee = 0,"
               " exercices_faits = 0 WHERE id = ?", (objectif, ex_id, seance_id))
    _ajouter(db, seance_id, OUVERTURE, message)
    return message


def repondre(db, eleve_id: int, seance_id: int, texte: str, tuteur=None, question: bool = False) -> dict:
    """Réponse à un message de l'élève. Renvoie {"reponse", "terminee"}.
    question : l'élève a touché « Poser une question » (grands) : c'est une question, pas une réponse."""
    etat = _etat(db, seance_id)
    ex_id = etat["exercice_en_cours"]
    if ex_id is None:  # plus d'exercice : la séance est finie
        return {"reponse": recapitulatif(db, eleve_id, seance_id), "terminee": True}
    notion, ex = EXERCICES[ex_id]
    choix = choix_de_l_enonce(ex["enonce"])
    ctx = _contexte(db, eleve_id, seance_id)

    (etape,) = db.execute("SELECT etape_cours FROM seances WHERE id = ?", (seance_id,)).fetchone()
    if etape is not None and not question:
        decoupee = etapes(notion)
        if texte == PAS_COMPRIS:  # l'IA réexplique cette étape (réponse gardée pour la prochaine fois)
            pseudo = {"enonce": decoupee[etape], "explication": decoupee[etape]}
            r = _demander_a_l_ia(db, eleve_id, seance_id, texte, pseudo, f"{notion}#etape{etape}", tuteur)
            return r
        if etape + 1 < len(decoupee):
            db.execute("UPDATE seances SET etape_cours = ? WHERE id = ?", (etape + 1, seance_id))
            message = _etape(decoupee, etape + 1)
        else:
            db.execute("UPDATE seances SET etape_cours = NULL WHERE id = ?", (seance_id,))
            message = f"✏️ هَيَّا نَتَمَرَّنُ!\n\n{ex['enonce']}"
        _ajouter(db, seance_id, texte, message)
        return {"reponse": message, "terminee": False}

    if question:
        return _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, ex_id, tuteur)
    if texte not in choix and texte != PAS_COMPRIS:
        # Texte écrit au clavier : contrôle gratuit (mots-clés, données personnelles) ; s'il y a un signal,
        # c'est l'IA (avec son contrôle complet et l'alerte au parent) qui répond.
        if detresse.detecter(texte) or filtres.masquer(texte)[1]:
            return _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, ex_id, tuteur, memoriser=False)

    if texte == PAS_COMPRIS:
        if etat["aide_donnee"] == 0:
            message = f"{ex['indice']}\n\n{ex['enonce']}"
            db.execute("UPDATE seances SET aide_donnee = 1 WHERE id = ?", (seance_id,))
        elif etat["aide_donnee"] == 1:
            message = f"{ex['explication']}\n\n{ex['enonce']}"
            db.execute("UPDATE seances SET aide_donnee = 2 WHERE id = ?", (seance_id,))
        else:
            return _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, ex_id, tuteur)
        _ajouter(db, seance_id, texte, message)
        return {"reponse": message, "terminee": False}

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


def _demander_a_l_ia(db, eleve_id, seance_id, texte, ex, ex_id, tuteur, memoriser=True) -> dict:
    """Seul cas payant : une question de l'élève (ou une incompréhension après l'explication).
    Une réponse déjà donnée à la même question sur le même exercice est réutilisée, sans appel à l'IA."""
    cle = normaliser(texte)
    if memoriser:
        deja = db.execute("SELECT reponse FROM reponses_ia WHERE exercice = ? AND question = ?", (ex_id, cle)).fetchone()
        if deja:
            db.execute("UPDATE reponses_ia SET utilisations = utilisations + 1 WHERE exercice = ? AND question = ?",
                       (ex_id, cle))
            message = f"{deja['reponse']}\n\n{ex['enonce']}"
            _ajouter(db, seance_id, texte, message)
            return {"reponse": message, "terminee": False}
    if tuteur is None:  # IA injoignable (clé absente) : on redonne l'explication stockée
        message = f"{ex['explication']}\n\n{ex['enonce']}"
        _ajouter(db, seance_id, texte, message)
        return {"reponse": message, "terminee": False}
    from agent.core import MESSAGE_INDISPONIBLE, MESSAGE_REFUS, TuteurIndisponible

    try:
        reponse = tuteur.repondre(db, eleve_id, seance_id, texte, boutons=(PAS_COMPRIS,),
                                  consigne=CONSIGNE_QUESTION.format(enonce=ex["enonce"]), outils=False)
    except TuteurIndisponible:
        reponse = ex["explication"]
        _ajouter(db, seance_id, texte, f"{reponse}\n\n{ex['enonce']}")
        return {"reponse": f"{reponse}\n\n{ex['enonce']}", "terminee": False}
    alerte = db.execute("SELECT 1 FROM alertes WHERE seance_id = ? AND extrait = ?", (seance_id, texte[:300])).fetchone()
    (prenom,) = db.execute("SELECT prenom FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    if (memoriser and not alerte and reponse not in (MESSAGE_INDISPONIBLE, MESSAGE_REFUS)
            and normaliser(prenom) not in normaliser(reponse)):
        db.execute("INSERT OR IGNORE INTO reponses_ia (exercice, question, reponse, cree_le) VALUES (?, ?, ?, ?)",
                   (ex_id, cle, reponse, maintenant_iso()))
    return {"reponse": f"{reponse}\n\n{ex['enonce']}", "terminee": False}


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
