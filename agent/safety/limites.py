"""Durée des séances et pause imposée."""

import sqlite3
from datetime import datetime, timedelta

from agent.db_utils import maintenant

DUREE_MAX_MINUTES = {"P1": 20, "P2": 45}
PAUSE_MINUTES = 15


def temps_ecoule(debut_iso: str, profil: str) -> bool:
    debut = datetime.fromisoformat(debut_iso)
    return maintenant() - debut >= timedelta(minutes=DUREE_MAX_MINUTES.get(profil, 30))


def pause_restante(db: sqlite3.Connection, eleve_id: int) -> int:
    """Minutes de pause restantes après une séance arrêtée parce que le temps était écoulé (0 si aucune)."""
    ligne = db.execute(
        "SELECT fin FROM seances WHERE eleve_id = ? AND fin_raison = 'temps' ORDER BY fin DESC LIMIT 1",
        (eleve_id,),
    ).fetchone()
    if ligne is None:
        return 0
    reste = datetime.fromisoformat(ligne["fin"]) + timedelta(minutes=PAUSE_MINUTES) - maintenant()
    return max(0, -(-int(reste.total_seconds()) // 60))
