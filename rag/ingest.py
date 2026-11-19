"""Découpe les documents de docs/ en passages et les indexe (SQLite FTS5).

    python3 -m rag.ingest        # réindexe tout (fait aussi automatiquement au démarrage de l'API)

Formats lus : .md, .txt, .docx. Le niveau d'un document se déduit de son nom ou de son dossier :
« cp » ou « p1 » -> P1, « 1ac » ou « p2 » -> P2 ; sinon il sert à tous les niveaux.
"""

import hashlib
import os
import re
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from rag.arabe import texte_indexe

FORMATS = {".md", ".txt", ".docx"}
TAILLE_MAX = 1500  # caractères par passage
_NIVEAUX = [(re.compile(r"(^|[^a-z0-9])(cp|p1)([^a-z0-9]|$)"), "P1"),
            (re.compile(r"(^|[^a-z0-9])(1ac|p2)([^a-z0-9]|$)"), "P2")]


def dossier_docs() -> Path:
    return Path(os.environ.get("TUTEUR_DOCS", "docs"))


def niveau_du_chemin(chemin: Path) -> str:
    nom = str(chemin).lower()
    for motif, niveau in _NIVEAUX:
        if motif.search(nom):
            return niveau
    return "tous"


def lire(chemin: Path) -> str:
    if chemin.suffix == ".docx":
        with zipfile.ZipFile(chemin) as z:
            racine = ElementTree.fromstring(z.read("word/document.xml"))
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lignes = []
        for p in racine.iter(f"{w}p"):
            style = p.find(f"{w}pPr/{w}pStyle")
            texte = "".join(t.text or "" for t in p.iter(f"{w}t"))
            if style is not None and style.get(f"{w}val", "").lower().startswith(("heading", "titre")):
                niveau = re.sub(r"\D", "", style.get(f"{w}val")) or "1"
                texte = "#" * min(int(niveau) + 1, 6) + " " + texte
            lignes.append(texte)
        return "\n".join(lignes)
    return chemin.read_text(encoding="utf-8")


def decouper(texte: str) -> list[tuple[str, str]]:
    """Passages (titre, texte) : un passage par section de titre, recoupé s'il est trop long.
    Le titre est le chemin des sections (sans le titre principal du document)."""
    passages, titres, corps = [], {}, []

    def vider():
        contenu = "\n".join(corps).strip()
        corps.clear()
        if not contenu:
            return
        chemin = [titres[k] for k in sorted(titres)]
        titre = " › ".join(chemin[1:] if len(chemin) > 1 else chemin)
        bloc = ""
        for para in re.split(r"\n\s*\n", contenu):
            if bloc and len(bloc) + len(para) > TAILLE_MAX:
                passages.append((titre, bloc.strip()))
                bloc = ""
            bloc += para + "\n\n"
        passages.append((titre, bloc.strip()))

    for ligne in texte.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)", ligne)
        if m:
            vider()
            profondeur = len(m.group(1))
            for k in [k for k in titres if k >= profondeur]:
                del titres[k]
            titres[profondeur] = m.group(2).strip()
        else:
            corps.append(ligne)
    vider()
    return passages


def indexer(db: sqlite3.Connection, dossier: Path | None = None) -> int:
    """Reconstruit l'index à partir de docs/. Renvoie le nombre de passages indexés."""
    dossier = dossier or dossier_docs()
    db.execute("DELETE FROM passages")
    # Table recréée à chaque fois : une base créée avec une ancienne version du schéma reste à jour.
    db.execute("DROP TABLE IF EXISTS passages_fts")
    db.execute("CREATE VIRTUAL TABLE passages_fts USING fts5(titre, contenu)")
    total = 0
    if not dossier.exists():
        return 0
    for chemin in sorted(p for p in dossier.rglob("*") if p.suffix.lower() in FORMATS and p.is_file()):
        texte = lire(chemin)
        source = chemin.relative_to(dossier.parent).as_posix()
        empreinte = hashlib.sha256(texte.encode()).hexdigest()[:12]
        niveau = niveau_du_chemin(chemin.relative_to(dossier))
        for titre, contenu in decouper(texte):
            pid = db.execute(
                "INSERT INTO passages (source, titre, niveau, texte, version) VALUES (?, ?, ?, ?, ?)",
                (source, titre, niveau, contenu, empreinte),
            ).lastrowid
            db.execute(
                "INSERT INTO passages_fts (rowid, titre, contenu) VALUES (?, ?, ?)",
                (pid, texte_indexe(titre), texte_indexe(contenu)),
            )
            total += 1
    return total


if __name__ == "__main__":
    from apps.api import db as base

    base.initialiser()
    conn = base.ouvrir()
    n = indexer(conn)
    conn.commit()
    print(f"{n} passages indexés depuis {dossier_docs()}/")
