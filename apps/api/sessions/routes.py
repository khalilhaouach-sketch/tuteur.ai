"""Séances de travail de l'élève avec l'agent tuteur."""

import json
import logging
from functools import lru_cache

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agent import seance_locale
from agent.core import LONGUEUR_MAX_MESSAGE, PROFILS, Tuteur, TuteurIndisponible
from agent.safety import limites
from agent.tools import Contexte
from agent.tools.rapport_parent import rediger
from apps.api.auth.routes import eleve_connecte
from apps.api.db import get_db, iso, maintenant

router = APIRouter(tags=["séances"])

MAX_MESSAGES_PAR_SEANCE = 60
# Réponses simples proposées en boutons au CP (mêmes valeurs que dans apps/web/student/index.html).
REPONSES_CP = ("نَعَمْ", "لَا", "لَمْ أَفْهَمْ")
# Profils dont les séances sont menées sans IA (l'IA ne répond qu'aux messages libres).
MODE_SANS_IA = {"P1", "P2"}


@lru_cache
def _client_anthropic():
    # La clé est lue dans la variable d'environnement ANTHROPIC_API_KEY, jamais dans le code.
    return anthropic.Anthropic()


def get_tuteur() -> Tuteur | None:
    """Remplacé par un faux client dans les tests (aucun appel réel à l'API).
    None si le client Claude ne peut pas être créé (clé absente) : les séances sans IA fonctionnent quand même."""
    try:
        return Tuteur(_client_anthropic())
    except anthropic.AnthropicError as e:  # ex. clé API absente
        logging.getLogger("tuteur").error("Client Claude impossible à créer : %s", e)
        return None


def _exiger(tuteur: Tuteur | None) -> Tuteur:
    if tuteur is None:
        raise _indisponible()
    return tuteur


class Debut(BaseModel):
    nombre: int | None = Field(default=None, ge=1, le=50)  # nombre d'exercices choisi par l'enfant


class Message(BaseModel):
    texte: str = Field(min_length=1, max_length=LONGUEUR_MAX_MESSAGE)
    question: bool = False  # « Poser une question » : à l'IA, pas à la correction


def _indisponible():
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, "Le tuteur est momentanément indisponible. Réessaie plus tard."
    )


MESSAGE_FIN_TEMPS = "اِنْتَهَى وَقْتُ الحِصَّةِ. خُذْ قِسْطًا مِنَ الرَّاحَةِ، وَإِلَى اللِّقَاءِ!"
RECAP_SECOURS = "أَحْسَنْتَ! إِلَى اللِّقَاءِ فِي الحِصَّةِ القَادِمَةِ."


def _seance_ouverte(db, seance_id: int, eleve_id: int):
    seance = db.execute(
        "SELECT s.id, s.fin, s.debut, s.mode, e.profil FROM seances s JOIN eleves e ON e.id = s.eleve_id"
        " WHERE s.id = ? AND s.eleve_id = ?", (seance_id, eleve_id)
    ).fetchone()
    if seance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Séance introuvable.")
    if seance["fin"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette séance est terminée.")
    return seance


def choix_en_cours(db, seance_id: int) -> list[str]:
    """Choix de l'exercice en cours (boutons du CP) : ceux du dernier exercice proposé,
    tant qu'il n'est pas terminé (réussi, ou expliqué après deux erreurs)."""
    (journal,) = db.execute("SELECT journal FROM seances WHERE id = ?", (seance_id,)).fetchone()
    for message in reversed(json.loads(journal)):
        if message["role"] != "user" or not isinstance(message["content"], list):
            continue
        for bloc in reversed(message["content"]):
            if bloc.get("type") != "tool_result" or bloc.get("is_error"):
                continue
            try:
                resultat = json.loads(bloc["content"])
            except (TypeError, json.JSONDecodeError):
                continue
            if resultat.get("exercice_termine"):
                return (resultat.get("exercice_suivant") or {}).get("choix", [])
            if "choix" in resultat:
                return resultat["choix"]
    return []


@router.post("/eleve/seances", status_code=status.HTTP_201_CREATED)
def commencer(debut: Debut | None = None, eleve_id: int = Depends(eleve_connecte), db=Depends(get_db),
              tuteur=Depends(get_tuteur)):
    profil, palier, par_defaut = db.execute(
        "SELECT profil, palier, exercices_par_seance FROM eleves WHERE id = ?", (eleve_id,)
    ).fetchone()
    if profil not in PROFILS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ce profil sera bientôt disponible.")
    if palier is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Fais d'abord le petit test pour savoir où tu en es (ou demande à ton parent de choisir ton palier).",
        )
    pause = limites.pause_restante(db, eleve_id)
    if pause:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, f"C'est l'heure de la pause : tu pourras reprendre dans {pause} min."
        )
    now = iso(maintenant())
    # Une seule séance ouverte à la fois.
    db.execute(
        "UPDATE seances SET fin = ?, fin_raison = 'nouvelle' WHERE eleve_id = ? AND fin IS NULL", (now, eleve_id)
    )
    seance_id = db.execute(
        "INSERT INTO seances (eleve_id, debut) VALUES (?, ?)", (eleve_id, now)
    ).lastrowid
    if profil in MODE_SANS_IA:
        # Séance menée par le serveur à partir des contenus stockés : aucun appel à l'API pour l'ouvrir.
        objectif = (debut.nombre if debut and debut.nombre else None) or par_defaut
        reponse = seance_locale.ouvrir(db, eleve_id, seance_id, objectif)
        return {"seance_id": seance_id, "reponse": reponse, "choix": seance_locale.choix_courants(db, seance_id),
                "profil": profil, "objectif": objectif}
    try:
        reponse = _exiger(tuteur).ouvrir_seance(db, eleve_id, seance_id)
    except TuteurIndisponible:
        raise _indisponible()
    return {"seance_id": seance_id, "reponse": reponse, "choix": choix_en_cours(db, seance_id), "profil": profil}


@router.post("/eleve/seances/{seance_id}/messages")
def envoyer(
    seance_id: int,
    message: Message,
    eleve_id: int = Depends(eleve_connecte),
    db=Depends(get_db),
    tuteur=Depends(get_tuteur),
):
    seance = _seance_ouverte(db, seance_id, eleve_id)
    if limites.temps_ecoule(seance["debut"], seance["profil"]):
        recap = _cloturer(db, tuteur, eleve_id, seance_id, "temps")
        return {"reponse": recap + "\n\n" + MESSAGE_FIN_TEMPS, "terminee": True}
    (nombre,) = db.execute(
        "SELECT json_array_length(journal) FROM seances WHERE id = ?", (seance_id,)
    ).fetchone()
    if nombre >= MAX_MESSAGES_PAR_SEANCE * 3:
        raise HTTPException(status.HTTP_409_CONFLICT, "Séance trop longue : termine-la et fais une pause.")
    if seance["mode"] == "local":
        r = seance_locale.repondre(db, eleve_id, seance_id, message.texte.strip(), tuteur, message.question)
        if r["terminee"]:
            _fermer(db, eleve_id, seance_id, "eleve")
        return {"reponse": r["reponse"], "choix": seance_locale.choix_courants(db, seance_id), "terminee": r["terminee"]}
    try:
        boutons = tuple(choix_en_cours(db, seance_id)) + (REPONSES_CP if seance["profil"] == "P1" else ())
        reponse = _exiger(tuteur).repondre(db, eleve_id, seance_id, message.texte, boutons)
    except TuteurIndisponible:
        raise _indisponible()
    return {"reponse": reponse, "choix": choix_en_cours(db, seance_id), "terminee": False}


@router.post("/eleve/seances/{seance_id}/fin")
def terminer(
    seance_id: int, eleve_id: int = Depends(eleve_connecte), db=Depends(get_db), tuteur=Depends(get_tuteur)
):
    _seance_ouverte(db, seance_id, eleve_id)
    return {"reponse": _cloturer(db, tuteur, eleve_id, seance_id, "eleve"), "terminee": True}


def _cloturer(db, tuteur: Tuteur, eleve_id: int, seance_id: int, raison: str) -> str:
    """Récapitulatif pour l'élève, fin de séance et bilan du jour pour le parent."""
    (mode,) = db.execute("SELECT mode FROM seances WHERE id = ?", (seance_id,)).fetchone()
    if mode == "local":
        recapitulatif = seance_locale.conclure(db, eleve_id, seance_id)
    else:
        try:
            recapitulatif = _exiger(tuteur).conclure(db, eleve_id, seance_id)
        except (TuteurIndisponible, HTTPException):
            recapitulatif = RECAP_SECOURS
    _fermer(db, eleve_id, seance_id, raison)
    return recapitulatif


def _fermer(db, eleve_id: int, seance_id: int, raison: str) -> None:
    db.execute(
        "UPDATE seances SET fin = ?, fin_raison = ? WHERE id = ?", (iso(maintenant()), raison, seance_id)
    )
    rediger(Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil=""), 1)
