"""Recherche des passages de docs/ les plus pertinents pour une question."""

import sqlite3

from rag.arabe import requete_fts


def chercher(db: sqlite3.Connection, question: str, niveau: str, limite: int = 3) -> list[dict]:
    requete = requete_fts(question)
    if not requete:
        return []
    lignes = db.execute(
        "SELECT p.source, p.titre, p.texte, bm25(passages_fts, 1.0) AS score FROM passages_fts"
        " JOIN passages p ON p.id = passages_fts.rowid"
        " WHERE passages_fts MATCH ? AND p.niveau IN (?, 'tous')"
        " ORDER BY score LIMIT ?",
        (requete, niveau, limite),
    ).fetchall()
    return [
        {"texte": l["texte"], "reference": f"{l['source']} — {l['titre']}" if l["titre"] else l["source"]}
        for l in lignes
    ]
