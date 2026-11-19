"""Phase 3 : indexation de docs/ et recherche des passages (lire_programme)."""

import sqlite3
import zipfile
from pathlib import Path

import pytest

from agent.tools import Contexte, executer
from rag.arabe import normaliser, racine_legere, requete_fts
from rag.ingest import decouper, indexer, niveau_du_chemin
from rag.search import chercher

SCHEMA = Path("db/schema.sql").read_text(encoding="utf-8")


@pytest.fixture
def base():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@pytest.fixture
def base_indexee(base):
    indexer(base, Path("docs"))
    return base


# --- Arabe ---------------------------------------------------------------------

def test_normalisation_ignore_voyelles_hamza_et_ta_marbuta():
    assert normaliser("الفَاعِلُ") == normaliser("الفاعل")
    assert normaliser("أَرْنَبٌ") == normaliser("ارنب")
    assert normaliser("دَجَاجَةٌ") == normaliser("دجاجه")


def test_prefixes_retires():
    assert racine_legere("والفاعل") == "فاعل"
    assert racine_legere("الباء") == "باء"
    assert racine_legere("بال") == "بال"  # mot trop court : inchangé
    assert requete_fts("ما هو ؟") is None  # seulement des mots vides


# --- Découpage et niveaux ------------------------------------------------------

def test_decoupage_par_sections():
    texte = "# Doc\nintro\n## A\ntexte a\n### A1\ntexte a1\n## B\ntexte b\n"
    assert decouper(texte) == [("Doc", "intro"), ("A", "texte a"), ("A › A1", "texte a1"), ("B", "texte b")]


def test_passages_trop_longs_recoupes():
    texte = "## Long\n" + "\n\n".join("ا" * 600 for _ in range(5))
    passages = decouper(texte)
    assert len(passages) > 1 and all(len(t) <= 1500 for _, t in passages)


def test_niveau_deduit_du_nom():
    assert niveau_du_chemin(Path("programmes/cp_arabe.md")) == "P1"
    assert niveau_du_chemin(Path("cours/2ac_exemples.md")) == "P2"
    assert niveau_du_chemin(Path("cours/P3/redaction.md")) == "P3"
    assert niveau_du_chemin(Path("pedagogie.md")) == "tous"
    assert niveau_du_chemin(Path("cours/capitale.md")) == "tous"  # « cp » doit être un mot entier


# --- Recherche sur les vrais documents -----------------------------------------

@pytest.mark.parametrize("question, section", [
    ("حرف الباء", "حرف الباء (ب)"),
    ("الثَّاء", "حرف الثاء (ث)"),
    ("حرف الضاد", "حرف الضاد (ض)"),
])
def test_trois_notions_du_cp(base_indexee, question, section):
    resultats = chercher(base_indexee, question, "P1")
    assert section in resultats[0]["reference"]
    assert resultats[0]["reference"].startswith("docs/programmes/cp_arabe.md")


def test_notion_2ac(base_indexee):
    resultats = chercher(base_indexee, "والفاعلُ", "P2")
    assert resultats[0]["reference"] == "docs/cours/2ac_exemples.md — الفاعل"
    assert "اسم مرفوع" in resultats[0]["texte"]


def test_niveau_respecte(base_indexee):
    # Un élève de 2AC ne reçoit pas les fiches du CP, et inversement.
    assert all("cp_arabe" not in r["reference"] for r in chercher(base_indexee, "حرف الباء", "P2"))
    assert chercher(base_indexee, "المفعول به", "P1") == [] or all(
        "2ac" not in r["reference"] for r in chercher(base_indexee, "المفعول به", "P1"))


def test_reindexation_sans_doublons(base_indexee):
    n = base_indexee.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    indexer(base_indexee, Path("docs"))
    assert base_indexee.execute("SELECT COUNT(*) FROM passages").fetchone()[0] == n
    assert base_indexee.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0] == n


def test_document_word(base, tmp_path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (f'<w:document xmlns:w="{w}"><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>المبتدأ والخبر</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>المبتدأ اسم مرفوع نبدأ به الجملة الاسمية.</w:t></w:r></w:p>'
           '</w:body></w:document>')
    docs = tmp_path / "docs" / "cours"
    docs.mkdir(parents=True)
    with zipfile.ZipFile(docs / "2ac_mobtada.docx", "w") as z:
        z.writestr("word/document.xml", xml)
    assert indexer(base, tmp_path / "docs") == 1
    r = chercher(base, "المبتدأ", "P2")
    assert r[0]["reference"] == "docs/cours/2ac_mobtada.docx — المبتدأ والخبر"


# --- L'outil lire_programme ----------------------------------------------------

def test_lire_programme_cite_ses_sources(base_indexee):
    ctx = Contexte(db=base_indexee, eleve_id=1, seance_id=None, profil="P2")
    sortie = executer(ctx, "lire_programme", {"notion": "كان وأخواتها"})
    assert sortie["passages"][0]["reference"] == "docs/cours/2ac_exemples.md — كان وأخواتها"


def test_lire_programme_sans_resultat(base_indexee):
    ctx = Contexte(db=base_indexee, eleve_id=1, seance_id=None, profil="P2")
    sortie = executer(ctx, "lire_programme", {"notion": "البلاغة والعروض"})
    assert sortie["passages"] == [] and "Aucun passage" in sortie["message"]
