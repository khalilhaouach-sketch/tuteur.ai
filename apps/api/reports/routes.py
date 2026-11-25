"""Espace parent : tableau de bord, progression, journal des séances, alertes, bilans."""

import json

from fastapi import APIRouter, Depends, HTTPException, status

from agent.tools import Contexte
from agent.tools.rapport_parent import rediger
from apps.api.auth.routes import _eleve_du_parent, parent_connecte
from apps.api.db import get_db, iso, maintenant

router = APIRouter(tags=["espace parent"])

OUTILS_LISIBLES = {
    "lire_programme": "consulte le cours",
    "generer_exercice": "propose un exercice",
    "corriger": "corrige la réponse",
    "enregistrer_progression": "enregistre la progression",
    "planifier_revision": "planifie une révision",
    "rapport_parent": "rédige un bilan",
}


@router.get("/parents/tableau")
def tableau(parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Les élèves du parent, avec leurs alertes non lues et leur dernière séance."""
    lignes = db.execute(
        "SELECT e.id, e.prenom, e.profil, e.palier,"
        " (SELECT COUNT(*) FROM alertes a WHERE a.eleve_id = e.id AND a.vue_le IS NULL) AS alertes,"
        " (SELECT MAX(debut) FROM seances s WHERE s.eleve_id = e.id) AS derniere_seance"
        " FROM eleves e WHERE e.parent_id = ? ORDER BY e.id",
        (parent_id,),
    ).fetchall()
    from agent import parcours

    return [{**dict(l), "palier": parcours.numero_de(l["palier"])} for l in lignes]


@router.get("/eleves/{eleve_id}/progression")
def progression(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    lignes = db.execute(
        "SELECT n.intitule AS notion, m.niveau AS maitrise, m.prochaine_revision,"
        " (SELECT COUNT(DISTINCT t.exercice) FROM tentatives t WHERE t.eleve_id = m.eleve_id AND t.notion_id = n.id) AS exercices,"
        " (SELECT COUNT(DISTINCT t.exercice) FROM tentatives t WHERE t.eleve_id = m.eleve_id AND t.notion_id = n.id"
        "  AND t.verdict = 'juste') AS reussis,"
        " (SELECT t.type_erreur FROM tentatives t WHERE t.eleve_id = m.eleve_id AND t.notion_id = n.id"
        "  AND t.type_erreur IS NOT NULL GROUP BY t.type_erreur ORDER BY COUNT(*) DESC LIMIT 1) AS erreur_frequente"
        " FROM maitrise m JOIN notions n ON n.id = m.notion_id WHERE m.eleve_id = ? ORDER BY n.intitule",
        (eleve_id,),
    ).fetchall()
    return [dict(l) for l in lignes]


@router.get("/eleves/{eleve_id}/seances")
def seances(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    lignes = db.execute(
        "SELECT s.id, s.debut, s.fin, s.fin_raison, ROUND(s.cout_dollars, 3) AS cout_dollars,"
        " (SELECT COUNT(*) FROM alertes a WHERE a.seance_id = s.id) AS alertes"
        " FROM seances s WHERE s.eleve_id = ? ORDER BY s.debut DESC LIMIT 50",
        (eleve_id,),
    ).fetchall()
    return [dict(l) for l in lignes]


def journal_lisible(messages: list[dict]) -> list[dict]:
    """Transforme le journal technique (format de l'API) en échanges lisibles par le parent."""
    sortie = []
    for m in messages:
        contenu = m["content"]
        if m["role"] == "user" and isinstance(contenu, str):
            if not contenu.startswith("[L'élève"):  # marqueurs techniques d'ouverture et de fin
                sortie.append({"qui": "eleve", "texte": contenu})
        elif m["role"] == "assistant" and isinstance(contenu, list):
            for bloc in contenu:
                if bloc.get("type") == "text" and bloc.get("text", "").strip():
                    sortie.append({"qui": "tuteur", "texte": bloc["text"]})
                elif bloc.get("type") == "tool_use":
                    precision = bloc["input"].get("notion") or bloc["input"].get("exercice_id") or ""
                    action = OUTILS_LISIBLES.get(bloc["name"], bloc["name"])
                    sortie.append({"qui": "outil", "texte": f"{action}{' : ' + precision if precision else ''}"})
        elif m["role"] == "user" and isinstance(contenu, list):
            for bloc in contenu:
                if bloc.get("type") != "tool_result" or bloc.get("is_error"):
                    continue
                try:
                    resultat = json.loads(bloc["content"])
                except (TypeError, json.JSONDecodeError):
                    continue
                refs = [p["reference"] for p in resultat.get("passages", [])]
                if refs:
                    sortie.append({"qui": "outil", "texte": "sources : " + " ; ".join(refs)})
                if "verdict" in resultat:
                    detail = resultat.get("type_erreur") or ""
                    sortie.append({"qui": "outil", "texte": f"verdict : {resultat['verdict']}{' (' + detail + ')' if detail else ''}"})
    return sortie


@router.get("/eleves/{eleve_id}/seances/{seance_id}/journal")
def journal(eleve_id: int, seance_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    ligne = db.execute(
        "SELECT journal FROM seances WHERE id = ? AND eleve_id = ?", (seance_id, eleve_id)
    ).fetchone()
    if ligne is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Séance introuvable.")
    return journal_lisible(json.loads(ligne["journal"]))


@router.get("/eleves/{eleve_id}/alertes")
def alertes(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    lignes = db.execute(
        "SELECT id, seance_id, type, extrait, cree_le, vue_le FROM alertes WHERE eleve_id = ? ORDER BY id DESC",
        (eleve_id,),
    ).fetchall()
    return [dict(l) for l in lignes]


@router.post("/eleves/{eleve_id}/alertes/{alerte_id}/vue", status_code=status.HTTP_204_NO_CONTENT)
def alerte_vue(eleve_id: int, alerte_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    curseur = db.execute(
        "UPDATE alertes SET vue_le = ? WHERE id = ? AND eleve_id = ? AND vue_le IS NULL",
        (iso(maintenant()), alerte_id, eleve_id),
    )
    if curseur.rowcount == 0 and db.execute(
        "SELECT 1 FROM alertes WHERE id = ? AND eleve_id = ?", (alerte_id, eleve_id)
    ).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerte introuvable.")


@router.get("/eleves/{eleve_id}/rapports")
def rapports(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    lignes = db.execute(
        "SELECT periode_debut, periode_fin, texte, cree_le FROM rapports WHERE eleve_id = ? ORDER BY id DESC LIMIT 20",
        (eleve_id,),
    ).fetchall()
    return [dict(l) for l in lignes]


@router.post("/eleves/{eleve_id}/rapports", status_code=status.HTTP_201_CREATED)
def nouveau_rapport(
    eleve_id: int, periode_jours: int = 7, parent_id: int = Depends(parent_connecte), db=Depends(get_db)
):
    """Bilan à la demande, rédigé par l'outil rapport_parent (à partir des résultats enregistrés)."""
    _eleve_du_parent(db, eleve_id, parent_id)
    if periode_jours not in (1, 7, 30):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Période : 1, 7 ou 30 jours.")
    texte = rediger(Contexte(db=db, eleve_id=eleve_id, seance_id=None, profil=""), periode_jours)
    return {"texte": texte}
