"""Comptes parents et sous-comptes élèves."""

import os
import re
import sqlite3
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from apps.api.auth import securite
from apps.api.db import get_db, iso, maintenant

router = APIRouter()

COOKIE_PARENT = "session_parent"
COOKIE_ELEVE = "session_eleve"
MAX_ELEVES_PAR_PARENT = 10

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Lettres (arabes ou latines), espaces, tirets et apostrophes : pas de chiffres ni de symboles.
_PRENOM = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")


def _cookie_securise() -> bool:
    return os.environ.get("TUTEUR_COOKIE_SECURE", "1") != "0"


def _poser_cookie(reponse: Response, nom: str, jeton: str, jours: int) -> None:
    reponse.set_cookie(
        nom,
        jeton,
        max_age=jours * 24 * 3600,
        httponly=True,
        secure=_cookie_securise(),
        samesite="lax",
    )


def _ip(requete: Request) -> str:
    return requete.client.host if requete.client else "inconnue"


# --- Modèles -----------------------------------------------------------------


class Inscription(BaseModel):
    email: str = Field(max_length=254)
    mot_de_passe: str = Field(min_length=8, max_length=128)
    consentement: bool

    @field_validator("email")
    @classmethod
    def email_valide(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("adresse e-mail invalide")
        return v


class Identifiants(BaseModel):
    email: str = Field(max_length=254)
    mot_de_passe: str = Field(max_length=128)


class NouvelEleve(BaseModel):
    prenom: str
    profil: Literal["P1", "P2"]

    @field_validator("prenom")
    @classmethod
    def prenom_valide(cls, v: str) -> str:
        v = " ".join(v.split())
        if not 1 <= len(v) <= 30 or not _PRENOM.match(v):
            raise ValueError("prénom invalide : lettres uniquement, 30 caractères au maximum")
        return v


class CodeAcces(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class Eleve(BaseModel):
    id: int
    prenom: str
    profil: str  # style : P1 enfant, P2 adolescent
    palier: int | None = None
    titre_palier: str | None = None
    dernier_palier: int | None = None
    exercices_par_seance: int = 10  # nombre d'exercices proposé à l'enfant (réglé par le parent)


class Reglages(BaseModel):
    exercices_par_seance: int = Field(ge=1, le=50)


# --- Qui est connecté ? --------------------------------------------------------


def parent_connecte(
    session_parent: str | None = Cookie(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> int:
    connexion = securite.lire_connexion(db, session_parent)
    if connexion is None or connexion["parent_id"] is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion parent requise.")
    return connexion["parent_id"]


def eleve_connecte(
    session_eleve: str | None = Cookie(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> int:
    connexion = securite.lire_connexion(db, session_eleve)
    if connexion is None or connexion["eleve_id"] is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Connexion élève requise.")
    return connexion["eleve_id"]


# --- Parents -----------------------------------------------------------------


@router.post("/parents/inscription", status_code=status.HTTP_201_CREATED, tags=["parents"])
def inscrire_parent(donnees: Inscription, reponse: Response, db=Depends(get_db)):
    # Sur un serveur public : une fois le compte de la famille créé, on ferme les inscriptions
    # (TUTEUR_INSCRIPTIONS=0), pour que personne d'autre n'utilise les crédits de l'API.
    if os.environ.get("TUTEUR_INSCRIPTIONS", "1") == "0":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Les inscriptions sont fermées sur ce tuteur.")
    if not donnees.consentement:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Le consentement du parent est obligatoire."
        )
    now = iso(maintenant())
    try:
        curseur = db.execute(
            "INSERT INTO parents (email, mot_de_passe_hash, consentement_le, cree_le)"
            " VALUES (?, ?, ?, ?)",
            (donnees.email, securite.hacher_mot_de_passe(donnees.mot_de_passe), now, now),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail.")
    jeton = securite.ouvrir_connexion(db, parent_id=curseur.lastrowid)
    _poser_cookie(reponse, COOKIE_PARENT, jeton, securite.DUREE_CONNEXION_PARENT_JOURS)
    return {"email": donnees.email}


@router.post("/parents/connexion", tags=["parents"])
def connecter_parent(donnees: Identifiants, reponse: Response, db=Depends(get_db)):
    email = donnees.email.strip().lower()
    cle = f"parent:{email}"
    if securite.trop_d_essais(db, cle, securite.MAX_ESSAIS_PARENT):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Trop d'essais. Réessayez dans 15 minutes."
        )
    parent = db.execute(
        "SELECT id, mot_de_passe_hash FROM parents WHERE email = ?", (email,)
    ).fetchone()
    stocke = parent["mot_de_passe_hash"] if parent else securite.EMPREINTE_FACTICE
    if not securite.verifier_mot_de_passe(donnees.mot_de_passe, stocke) or parent is None:
        securite.noter_essai_echoue(db, cle)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect.")
    jeton = securite.ouvrir_connexion(db, parent_id=parent["id"])
    _poser_cookie(reponse, COOKIE_PARENT, jeton, securite.DUREE_CONNEXION_PARENT_JOURS)
    return {"email": email}


@router.post("/parents/deconnexion", status_code=status.HTTP_204_NO_CONTENT, tags=["parents"])
def deconnecter_parent(
    reponse: Response, session_parent: str | None = Cookie(default=None), db=Depends(get_db)
):
    if session_parent:
        securite.fermer_connexion(db, session_parent)
    reponse.delete_cookie(COOKIE_PARENT)


@router.get("/parents/moi", tags=["parents"])
def parent_actuel(
    reponse: Response,
    parent_id: int = Depends(parent_connecte),
    session_parent: str | None = Cookie(default=None),
    db=Depends(get_db),
):
    # À chaque ouverture de l'espace parent, la session et son cookie repartent pour 30 jours.
    securite.prolonger_connexion(db, session_parent, securite.DUREE_CONNEXION_PARENT_JOURS)
    _poser_cookie(reponse, COOKIE_PARENT, session_parent, securite.DUREE_CONNEXION_PARENT_JOURS)
    ligne = db.execute("SELECT email FROM parents WHERE id = ?", (parent_id,)).fetchone()
    return {"email": ligne["email"]}


# --- Élèves (gérés par le parent) ----------------------------------------------


def _eleve_du_parent(db: sqlite3.Connection, eleve_id: int, parent_id: int) -> sqlite3.Row:
    ligne = db.execute(
        "SELECT id, prenom, profil FROM eleves WHERE id = ? AND parent_id = ?",
        (eleve_id, parent_id),
    ).fetchone()
    if ligne is None:  # même réponse si l'élève existe chez un autre parent
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Élève introuvable.")
    return ligne


@router.get("/eleves", response_model=list[Eleve], tags=["élèves"])
def lister_eleves(parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    lignes = db.execute(
        "SELECT id, prenom, profil, palier, exercices_par_seance FROM eleves WHERE parent_id = ? ORDER BY id",
        (parent_id,),
    ).fetchall()
    from agent import parcours

    return [{**dict(l), "palier": parcours.numero_de(l["palier"])} for l in lignes]


@router.post(
    "/eleves", response_model=Eleve, status_code=status.HTTP_201_CREATED, tags=["élèves"]
)
def ajouter_eleve(
    donnees: NouvelEleve, parent_id: int = Depends(parent_connecte), db=Depends(get_db)
):
    (nombre,) = db.execute(
        "SELECT COUNT(*) FROM eleves WHERE parent_id = ?", (parent_id,)
    ).fetchone()
    if nombre >= MAX_ELEVES_PAR_PARENT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{MAX_ELEVES_PAR_PARENT} élèves au maximum par compte."
        )
    curseur = db.execute(
        "INSERT INTO eleves (parent_id, prenom, profil, cree_le) VALUES (?, ?, ?, ?)",
        (parent_id, donnees.prenom, donnees.profil, iso(maintenant())),
    )
    return {"id": curseur.lastrowid, "prenom": donnees.prenom, "profil": donnees.profil}


@router.delete("/eleves/{eleve_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["élèves"])
def supprimer_eleve(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    _eleve_du_parent(db, eleve_id, parent_id)
    # Supprime aussi ses résultats, ses séances et déconnecte ses appareils (ON DELETE CASCADE).
    db.execute("DELETE FROM eleves WHERE id = ?", (eleve_id,))


@router.put("/eleves/{eleve_id}/reglages", tags=["élèves"])
def regler(eleve_id: int, reglages: Reglages, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Nombre d'exercices proposé à l'enfant au début de chaque séance (il peut en choisir un autre)."""
    _eleve_du_parent(db, eleve_id, parent_id)
    db.execute("UPDATE eleves SET exercices_par_seance = ? WHERE id = ?", (reglages.exercices_par_seance, eleve_id))
    return {"exercices_par_seance": reglages.exercices_par_seance}


@router.post("/eleves/{eleve_id}/deconnexion", tags=["élèves"])
def deconnecter_appareils(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Le parent déconnecte tous les appareils de l'enfant (ordinateur prêté, téléphone perdu...)."""
    _eleve_du_parent(db, eleve_id, parent_id)
    n = db.execute("DELETE FROM connexions WHERE eleve_id = ?", (eleve_id,)).rowcount
    return {"appareils_deconnectes": n}


@router.post("/eleves/{eleve_id}/code", tags=["élèves"])
def generer_code(eleve_id: int, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Code à 6 chiffres, valable 15 minutes et une seule fois, à taper sur l'appareil de l'élève."""
    _eleve_du_parent(db, eleve_id, parent_id)
    code, expire_le = securite.creer_code_acces(db, eleve_id)
    return {"code": code, "expire_le": expire_le}


# --- Élèves (côté appareil de l'élève) -----------------------------------------


@router.post("/eleve/connexion", response_model=Eleve, tags=["espace élève"])
def connecter_eleve(
    donnees: CodeAcces, requete: Request, reponse: Response, db=Depends(get_db)
):
    cle = f"code:{_ip(requete)}"
    if securite.trop_d_essais(db, cle, securite.MAX_ESSAIS_CODE):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Trop d'essais. Demande un nouveau code à ton parent."
        )
    eleve_id = securite.utiliser_code_acces(db, donnees.code)
    if eleve_id is None:
        securite.noter_essai_echoue(db, cle)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Code incorrect ou expiré.")
    jeton = securite.ouvrir_connexion(db, eleve_id=eleve_id)
    _poser_cookie(reponse, COOKIE_ELEVE, jeton, securite.DUREE_CONNEXION_ELEVE_JOURS)
    ligne = db.execute("SELECT id, prenom, profil FROM eleves WHERE id = ?", (eleve_id,)).fetchone()
    return dict(ligne)


@router.post("/eleve/deconnexion", status_code=status.HTTP_204_NO_CONTENT, tags=["espace élève"])
def deconnecter_eleve(
    reponse: Response, session_eleve: str | None = Cookie(default=None), db=Depends(get_db)
):
    """« Changer d'enfant » sur un appareil partagé : il faudra un nouveau code pour revenir."""
    if session_eleve:
        securite.fermer_connexion(db, session_eleve)
    reponse.delete_cookie(COOKIE_ELEVE)


@router.get("/eleve/moi", response_model=Eleve, tags=["espace élève"])
def eleve_actuel(eleve_id: int = Depends(eleve_connecte), db=Depends(get_db)):
    from agent import parcours

    ligne = dict(db.execute(
        "SELECT id, prenom, profil, palier, exercices_par_seance FROM eleves WHERE id = ?", (eleve_id,)
    ).fetchone())
    ligne["palier"] = parcours.numero_de(ligne["palier"])
    ligne["titre_palier"] = parcours.palier(ligne["palier"])["titre"] if ligne["palier"] else None
    ligne["dernier_palier"] = parcours.DERNIER
    return ligne
