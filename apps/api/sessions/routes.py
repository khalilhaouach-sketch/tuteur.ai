"""Séances de travail de l'élève avec l'agent tuteur."""

from functools import lru_cache

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agent.core import LONGUEUR_MAX_MESSAGE, PROFILS, Tuteur, TuteurIndisponible
from agent.tools import Contexte
from agent.tools.rapport_parent import rediger
from apps.api.auth.routes import eleve_connecte, parent_connecte, _eleve_du_parent
from apps.api.db import get_db, iso, maintenant

router = APIRouter(tags=["séances"])

MAX_MESSAGES_PAR_SEANCE = 60


@lru_cache
def _client_anthropic():
    # La clé est lue dans la variable d'environnement ANTHROPIC_API_KEY, jamais dans le code.
    return anthropic.Anthropic()


def get_tuteur() -> Tuteur:
    """Remplacé par un faux client dans les tests (aucun appel réel à l'API)."""
    try:
        return Tuteur(_client_anthropic())
    except anthropic.AnthropicError:  # ex. clé API absente
        raise _indisponible()


class Message(BaseModel):
    texte: str = Field(min_length=1, max_length=LONGUEUR_MAX_MESSAGE)


def _indisponible():
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, "Le tuteur est momentanément indisponible. Réessaie plus tard."
    )


def _seance_ouverte(db, seance_id: int, eleve_id: int):
    seance = db.execute(
        "SELECT id, fin FROM seances WHERE id = ? AND eleve_id = ?", (seance_id, eleve_id)
    ).fetchone()
    if seance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Séance introuvable.")
    if seance["fin"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette séance est terminée.")
    return seance


@router.post("/eleve/seances", status_code=status.HTTP_201_CREATED)
def commencer(eleve_id: int = Depends(eleve_connecte), db=Depends(get_db), tuteur=Depends(get_tuteur)):
    (profil,) = db.execute("SELECT profil FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    if profil not in PROFILS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ce profil sera bientôt disponible.")
    now = iso(maintenant())
    # Une seule séance ouverte à la fois.
    db.execute("UPDATE seances SET fin = ? WHERE eleve_id = ? AND fin IS NULL", (now, eleve_id))
    seance_id = db.execute(
        "INSERT INTO seances (eleve_id, debut) VALUES (?, ?)", (eleve_id, now)
    ).lastrowid
    try:
        reponse = tuteur.ouvrir_seance(db, eleve_id, seance_id)
    except TuteurIndisponible:
        raise _indisponible()
    return {"seance_id": seance_id, "reponse": reponse}


@router.post("/eleve/seances/{seance_id}/messages")
def envoyer(
    seance_id: int,
    message: Message,
    eleve_id: int = Depends(eleve_connecte),
    db=Depends(get_db),
    tuteur=Depends(get_tuteur),
):
    _seance_ouverte(db, seance_id, eleve_id)
    (nombre,) = db.execute(
        "SELECT json_array_length(journal) FROM seances WHERE id = ?", (seance_id,)
    ).fetchone()
    if nombre >= MAX_MESSAGES_PAR_SEANCE * 3:
        raise HTTPException(status.HTTP_409_CONFLICT, "Séance trop longue : termine-la et fais une pause.")
    try:
        return {"reponse": tuteur.repondre(db, eleve_id, seance_id, message.texte)}
    except TuteurIndisponible:
        raise _indisponible()


@router.post("/eleve/seances/{seance_id}/fin")
def terminer(
    seance_id: int, eleve_id: int = Depends(eleve_connecte), db=Depends(get_db), tuteur=Depends(get_tuteur)
):
    _seance_ouverte(db, seance_id, eleve_id)
    try:
        recapitulatif = tuteur.conclure(db, eleve_id, seance_id)
    except TuteurIndisponible:
        recapitulatif = "أَحْسَنْتَ! إِلَى اللِّقَاءِ فِي الحِصَّةِ القَادِمَةِ."
    db.execute("UPDATE seances SET fin = ? WHERE id = ?", (iso(maintenant()), seance_id))
    # Le bilan du jour part au parent (enregistré dans rapports).
    rediger(Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil=""), 1)
    return {"reponse": recapitulatif}


@router.get("/eleves/{eleve_id}/rapports", tags=["élèves"])
def rapports(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    lignes = db.execute(
        "SELECT periode_debut, periode_fin, texte FROM rapports WHERE eleve_id = ? ORDER BY id DESC LIMIT 20",
        (eleve_id,),
    ).fetchall()
    return [dict(l) for l in lignes]
