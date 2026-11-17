"""Accès à la base SQLite."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def chemin_base() -> str:
    return os.environ.get("TUTEUR_DB", "data/tuteur.db")


def ouvrir() -> sqlite3.Connection:
    chemin = chemin_base()
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialiser() -> None:
    """Crée les tables manquantes (sans effet sur les tables existantes)."""
    conn = ouvrir()
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        conn.close()


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


def maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def dans(**delai) -> str:
    return iso(maintenant() + timedelta(**delai))
