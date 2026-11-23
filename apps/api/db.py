"""Accès à la base SQLite."""

import os
import sqlite3
from datetime import timedelta
from pathlib import Path

from agent.db_utils import iso, maintenant  # noqa: F401 (réexportés)

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def chemin_base() -> str:
    return os.environ.get("TUTEUR_DB", "data/tuteur.db")


def ouvrir() -> sqlite3.Connection:
    chemin = chemin_base()
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    # Une connexion par requête : FastAPI peut l'ouvrir et la fermer dans des fils d'exécution
    # différents, mais jamais l'utiliser dans deux requêtes à la fois.
    conn = sqlite3.connect(chemin, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialiser() -> None:
    """Crée les tables manquantes (sans effet sur les tables existantes)."""
    conn = ouvrir()
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        _ajouter_colonnes_manquantes(conn)
        _paliers_en_identifiants(conn)
        conn.commit()
    finally:
        conn.close()


# Colonnes ajoutées après la création des premières bases (en attendant de vraies migrations).
_COLONNES_AJOUTEES = {
    "seances": {"fin_raison": "TEXT CHECK (fin_raison IN ('eleve', 'temps', 'nouvelle'))"},
    "eleves": {"palier": "TEXT"},
}


def _ajouter_colonnes_manquantes(conn: sqlite3.Connection) -> None:
    for table, colonnes in _COLONNES_AJOUTEES.items():
        existantes = {c[1] for c in conn.execute(f"PRAGMA table_info({table})")}
        for nom, definition in colonnes.items():
            if nom not in existantes:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {definition}")


def get_db():
    """Dépendance FastAPI : une connexion par requête, validée si tout s'est bien passé."""
    conn = ouvrir()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dans(**delai) -> str:
    return iso(maintenant() + timedelta(**delai))


def _paliers_en_identifiants(conn: sqlite3.Connection) -> None:
    """Bases de la première version : le palier était un numéro ; on le remplace par son identifiant fixe."""
    from agent.parcours import ANCIENS_IDS

    for table, colonne in (("eleves", "palier"), ("tests_palier", "palier_propose")):
        for numero, palier_id in enumerate(ANCIENS_IDS, 1):
            conn.execute(
                # Numéro stocké comme nombre (ancienne colonne INTEGER) ou comme texte (colonne TEXT).
                f"UPDATE {table} SET {colonne} = ? WHERE CAST({colonne} AS TEXT) = ?",
                (palier_id, str(numero)),
            )
