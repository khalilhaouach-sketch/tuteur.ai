"""Parcours en paliers : tests de positionnement et de passage (élève), suivi et confirmation (parent)."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agent import evaluation, parcours
from apps.api.auth.routes import _eleve_du_parent, eleve_connecte, parent_connecte
from apps.api.db import get_db

router = APIRouter(tags=["parcours"])

SEUIL_ACQUIS = 0.6  # maîtrise à partir de laquelle une leçon est considérée comme acquise


class NouveauTest(BaseModel):
    type: Literal["positionnement", "passage"]


class Reponse(BaseModel):
    reponse: str = Field(min_length=1, max_length=500)


class Decision(BaseModel):
    accepte: bool


class ChoixPalier(BaseModel):
    palier: int = Field(ge=1, le=parcours.DERNIER)


# --- Côté élève --------------------------------------------------------------------

@router.post("/eleve/tests", status_code=status.HTTP_201_CREATED)
def commencer_test(donnees: NouveauTest, eleve_id: int = Depends(eleve_connecte), db=Depends(get_db)):
    try:
        test_id = evaluation.commencer(db, eleve_id, donnees.type)
    except evaluation.TestImpossible as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {"test_id": test_id, "question": evaluation.question_courante(evaluation.charger(db, test_id, eleve_id))}


@router.post("/eleve/tests/{test_id}/reponses")
def repondre(test_id: int, donnees: Reponse, eleve_id: int = Depends(eleve_connecte), db=Depends(get_db)):
    test = evaluation.charger(db, test_id, eleve_id)
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test introuvable.")
    try:
        return evaluation.repondre(db, test, donnees.reponse)
    except evaluation.TestImpossible as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


# --- Côté parent ---------------------------------------------------------------------

@router.get("/eleves/{eleve_id}/parcours")
def suivi(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    actuel = parcours.palier_eleve(db, eleve_id)
    maitrise = {
        r["intitule"]: r["niveau"]
        for r in db.execute(
            "SELECT n.intitule, m.niveau FROM maitrise m JOIN notions n ON n.id = m.notion_id WHERE m.eleve_id = ?",
            (eleve_id,),
        )
    }
    paliers = []
    for p in parcours.PALIERS:
        acquises = sum(1 for n in p["notions"] if maitrise.get(n, 0) >= SEUIL_ACQUIS)
        etat = ("a_venir" if actuel is None or p["numero"] > actuel
                else "actuel" if p["numero"] == actuel else "valide")
        paliers.append({"numero": p["numero"], "titre": p["titre"], "description": p["description"],
                        "etat": etat, "lecons": len(p["notions"]), "lecons_acquises": acquises})
    tests = [
        {**dict(t), "palier_propose": parcours.numero_de(t["palier_propose"]),
         "titre_palier": parcours.palier(parcours.numero_de(t["palier_propose"]))["titre"] if t["palier_propose"] else None}
        for t in db.execute(
            "SELECT id, type, statut, palier_propose, score, cree_le, fini_le FROM tests_palier"
            " WHERE eleve_id = ? AND statut != 'abandonne' ORDER BY id DESC LIMIT 10",
            (eleve_id,),
        )
    ]
    return {"palier": actuel, "paliers": paliers, "tests": tests}


@router.post("/eleves/{eleve_id}/tests/{test_id}/decision")
def decider(eleve_id: int, test_id: int, donnees: Decision,
            parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    try:
        nouveau = evaluation.confirmer(db, test_id, eleve_id, donnees.accepte)
    except evaluation.TestImpossible as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {"palier": nouveau}


@router.put("/eleves/{eleve_id}/palier")
def choisir_palier(eleve_id: int, donnees: ChoixPalier,
                   parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Le parent place lui-même l'enfant sur un palier (sans test)."""
    _eleve_du_parent(db, eleve_id, parent_id)
    parcours.fixer_palier(db, eleve_id, donnees.palier)
    return {"palier": donnees.palier}
