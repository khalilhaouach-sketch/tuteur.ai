"""Appareil de la famille : le parent l'autorise une fois ; ensuite chaque enfant entre en touchant son prénom.

Le jeton (cookie « appareil_famille », un an) ne donne aucun droit parent : il permet seulement de choisir
un enfant de cette famille et d'ouvrir sa session sur cet appareil. Le parent peut retirer tous les appareils.
"""

import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from apps.api.auth import securite
from apps.api.auth.routes import COOKIE_ELEVE, _cookie_securise, _poser_cookie, parent_connecte
from apps.api.db import dans, get_db, iso, maintenant

router = APIRouter(tags=["appareil de la famille"])

COOKIE_FAMILLE = "appareil_famille"
DUREE_FAMILLE_JOURS = 365


def _parent_de_l_appareil(appareil_famille: str | None = Cookie(default=None), db=Depends(get_db)) -> int:
    if not appareil_famille:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cet appareil n'est pas un appareil de la famille.")
    ligne = db.execute(
        "SELECT parent_id FROM appareils_famille WHERE jeton_hash = ? AND expire_le > ?",
        (securite.empreinte(appareil_famille), iso(maintenant())),
    ).fetchone()
    if ligne is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cet appareil n'est pas un appareil de la famille.")
    return ligne["parent_id"]


@router.post("/parents/appareil-famille")
def autoriser_appareil(reponse: Response, parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    """Le parent, connecté sur l'appareil de la maison, l'autorise pour les enfants (plus besoin de code)."""
    jeton = secrets.token_urlsafe(32)
    db.execute("INSERT INTO appareils_famille (jeton_hash, parent_id, expire_le) VALUES (?, ?, ?)",
               (securite.empreinte(jeton), parent_id, dans(days=DUREE_FAMILLE_JOURS)))
    reponse.set_cookie(COOKIE_FAMILLE, jeton, max_age=DUREE_FAMILLE_JOURS * 24 * 3600, httponly=True,
                       secure=_cookie_securise(), samesite="lax")
    return {"autorise": True}


@router.post("/parents/appareils-famille/retirer")
def retirer_appareils(parent_id: int = Depends(parent_connecte), db=Depends(get_db)):
    n = db.execute("DELETE FROM appareils_famille WHERE parent_id = ?", (parent_id,)).rowcount
    return {"appareils_retires": n}


@router.get("/famille/eleves")
def enfants_de_la_famille(parent_id: int = Depends(_parent_de_l_appareil), db=Depends(get_db)):
    """Prénoms à afficher sur l'appareil de la famille (rien d'autre)."""
    return [dict(l) for l in db.execute(
        "SELECT id, prenom, profil FROM eleves WHERE parent_id = ? ORDER BY id", (parent_id,))]


@router.post("/famille/eleves/{eleve_id}/entrer")
def entrer(eleve_id: int, reponse: Response, parent_id: int = Depends(_parent_de_l_appareil), db=Depends(get_db)):
    if db.execute("SELECT 1 FROM eleves WHERE id = ? AND parent_id = ?", (eleve_id, parent_id)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Élève introuvable.")
    jeton = securite.ouvrir_connexion(db, eleve_id=eleve_id)
    _poser_cookie(reponse, COOKIE_ELEVE, jeton, securite.DUREE_CONNEXION_ELEVE_JOURS)
    return {"eleve_id": eleve_id}
